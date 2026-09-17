//! Relevance by embeddings: it finds meaning word overlap misses, reuses its cache, can be
//! rebuilt from nothing, and falls back to word overlap when the endpoint fails.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use sage_agents::embeddings::{Embedder, EmbeddingCache, HttpEmbedder, Relevance};
use sage_agents::llm::PromptParts;
use sage_agents::retrieval::Candidate;
use serde_json::{Value, json};

/// Embeds by topic: river travel, gates and locks, food, plus a constant so no vector is zero.
#[derive(Clone)]
struct TopicEmbedder {
    calls: Arc<Mutex<Vec<Vec<String>>>>,
    fail: bool,
}

impl TopicEmbedder {
    fn new() -> TopicEmbedder {
        TopicEmbedder {
            calls: Arc::new(Mutex::new(Vec::new())),
            fail: false,
        }
    }

    fn calls(&self) -> Vec<Vec<String>> {
        self.calls.lock().unwrap().clone()
    }
}

impl Embedder for TopicEmbedder {
    fn model(&self) -> &str {
        "topics-v1"
    }

    fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, String> {
        self.calls.lock().unwrap().push(texts.to_vec());
        if self.fail {
            return Err("endpoint is down".into());
        }
        let topics: [&[&str]; 3] = [
            &["ferry", "boat", "river", "crossing", "oars"],
            &["gate", "key", "lock", "stone"],
            &["bread", "cheese", "stew", "soup"],
        ];
        Ok(texts
            .iter()
            .map(|t| {
                let t = t.to_lowercase();
                let mut v: Vec<f32> = topics
                    .iter()
                    .map(|words| words.iter().filter(|w| t.contains(*w)).count() as f32)
                    .collect();
                v.push(0.1);
                v
            })
            .collect())
    }
}

fn candidate(tick: u64, text: &str) -> Candidate {
    Candidate {
        tick,
        text: text.into(),
        importance: 4.0,
    }
}

/// An old line about the boat, 20 about food, then 5 recent ones: none shares a word with the
/// question about the ferry.
fn parts() -> PromptParts {
    let mut candidates = vec![candidate(1, "Bo says, \"The boat crosses at dawn.\"")];
    for tick in 2..22 {
        candidates.push(candidate(
            tick,
            &format!("Cy says, \"More bread and cheese {tick}?\""),
        ));
    }
    for tick in 22..27 {
        candidates.push(candidate(tick, &format!("Cy says, \"Stew again {tick}.\"")));
    }
    PromptParts {
        system: "system".into(),
        name: "Wren".into(),
        candidates,
        query: "Dock Bo When does the ferry leave?".into(),
        now: 30,
        ask: "What does Wren do next?".into(),
    }
}

fn shown(parts: &PromptParts, relevance: &[f64]) -> String {
    parts.assemble(relevance)[1].content.clone()
}

#[test]
fn embeddings_find_what_word_overlap_misses() {
    let parts = parts();
    let lexical = shown(&parts, &Relevance::Lexical.score(&parts).0);
    assert!(
        !lexical.contains("boat"),
        "word overlap cannot see it: {lexical}"
    );

    let relevance = Relevance::embedded(TopicEmbedder::new(), EmbeddingCache::in_memory().unwrap());
    let (scores, warning) = relevance.score(&parts);
    assert!(warning.is_none());
    assert!(scores[0] > 0.9, "boat vs ferry: {}", scores[0]);
    assert!(scores[1] < 0.2, "bread vs ferry: {}", scores[1]);
    assert!(shown(&parts, &scores).contains("The boat crosses at dawn."));
}

#[test]
fn the_cache_saves_calls_and_can_be_rebuilt_from_nothing() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("world.db.embeddings.db");
    let embedder = TopicEmbedder::new();
    let mut parts = parts();

    let relevance = Relevance::embedded(embedder.clone(), EmbeddingCache::open(&path).unwrap());
    let first = relevance.score(&parts).0;
    assert_eq!(embedder.calls().len(), 1);
    assert_eq!(
        embedder.calls()[0].len(),
        27,
        "query and 26 candidates in one batch"
    );
    relevance.score(&parts);
    assert_eq!(embedder.calls().len(), 1, "everything was cached");

    parts
        .candidates
        .push(candidate(28, "Bo says, \"Row the boat.\""));
    relevance.score(&parts);
    assert_eq!(embedder.calls().len(), 2);
    assert_eq!(embedder.calls()[1], ["Bo says, \"Row the boat.\""]);
    drop(relevance);

    // A fresh process with the same file needs no calls at all.
    let reopened = Relevance::embedded(embedder.clone(), EmbeddingCache::open(&path).unwrap());
    reopened.score(&parts);
    assert_eq!(embedder.calls().len(), 2);
    drop(reopened);

    // Deleting the cache loses nothing but time.
    std::fs::remove_file(&path).unwrap();
    let rebuilt = Relevance::embedded(embedder.clone(), EmbeddingCache::open(&path).unwrap());
    parts.candidates.pop();
    assert_eq!(rebuilt.score(&parts).0, first);
    assert_eq!(embedder.calls().len(), 3);
}

#[test]
fn a_failing_endpoint_falls_back_to_word_overlap_and_rests() {
    let parts = parts();
    let embedder = TopicEmbedder {
        fail: true,
        ..TopicEmbedder::new()
    };
    let relevance = Relevance::embedded(embedder.clone(), EmbeddingCache::in_memory().unwrap());

    let (scores, warning) = relevance.score(&parts);
    assert_eq!(scores, Relevance::Lexical.score(&parts).0);
    assert!(warning.unwrap().contains("endpoint is down"));

    let (again, quiet) = relevance.score(&parts);
    assert_eq!(again, scores);
    assert!(quiet.is_none(), "one warning per failure, not per request");
    assert_eq!(
        embedder.calls().len(),
        1,
        "resting: the endpoint is not asked again yet"
    );
}

#[test]
fn http_embedder_speaks_the_openai_format() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}/v1", listener.local_addr().unwrap());
    let seen = Arc::new(Mutex::new(Vec::<(String, Value)>::new()));
    let record = Arc::clone(&seen);
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let mut stream = stream.unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut request_line = String::new();
            reader.read_line(&mut request_line).unwrap();
            let mut length = 0;
            loop {
                let mut line = String::new();
                reader.read_line(&mut line).unwrap();
                let line = line.trim_end().to_ascii_lowercase();
                if line.is_empty() {
                    break;
                }
                if let Some(v) = line.strip_prefix("content-length:") {
                    length = v.trim().parse().unwrap();
                }
            }
            let mut body = vec![0; length];
            reader.read_exact(&mut body).unwrap();
            let body: Value = serde_json::from_slice(&body).unwrap();
            let count = body["input"].as_array().unwrap().len();
            record
                .lock()
                .unwrap()
                .push((request_line.trim().to_owned(), body));
            // Answer out of order, as the index field allows.
            let data: Vec<Value> = (0..count)
                .rev()
                .map(|i| json!({"index": i, "embedding": [i as f64, 1.0]}))
                .collect();
            let reply = json!({ "data": data }).to_string();
            let _ = write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{reply}",
                reply.len()
            );
        }
    });

    let embedder = HttpEmbedder::new(url, "nomic-embed-text".into(), None, Duration::from_secs(5));
    let vectors = embedder
        .embed(&["a".into(), "b".into(), "c".into()])
        .unwrap();
    assert_eq!(vectors, [vec![0.0, 1.0], vec![1.0, 1.0], vec![2.0, 1.0]]);
    let seen = seen.lock().unwrap();
    assert_eq!(seen[0].0, "POST /v1/embeddings HTTP/1.1");
    assert_eq!(seen[0].1["model"], "nomic-embed-text");
    assert_eq!(seen[0].1["input"], json!(["a", "b", "c"]));
}
