//! Relevance by meaning. Memory texts and the current situation are embedded by an
//! OpenAI-compatible `/embeddings` endpoint and compared by cosine similarity.
//!
//! Embeddings are a cache, never part of the world: they live in their own SQLite file beside
//! the world, keyed by model and exact text, and deleting that file only costs time. When the
//! endpoint fails, relevance falls back to word overlap and the embedder rests for a while.

use std::path::Path;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use rusqlite::{Connection, OptionalExtension, params};
use serde_json::{Value, json};

use crate::llm::PromptParts;

/// How long the embedder rests after a failure before it is tried again.
pub const EMBEDDER_REST: Duration = Duration::from_secs(60);

/// Turns texts into vectors.
pub trait Embedder: Send + Sync + 'static {
    /// The model name, part of every cache key.
    fn model(&self) -> &str;

    /// One vector per text, in order. Blocking; runs on a worker thread.
    fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, String>;
}

/// OpenAI-compatible `POST {url}/embeddings`.
pub struct HttpEmbedder {
    url: String,
    model: String,
    api_key: Option<String>,
    agent: ureq::Agent,
}

impl HttpEmbedder {
    /// An embedder for `model` at `url`, e.g. `http://localhost:11434/v1` and
    /// `nomic-embed-text` for Ollama.
    pub fn new(url: String, model: String, api_key: Option<String>, timeout: Duration) -> Self {
        let agent = ureq::Agent::config_builder()
            .timeout_global(Some(timeout))
            .http_status_as_error(false)
            .build()
            .into();
        HttpEmbedder {
            url,
            model,
            api_key,
            agent,
        }
    }
}

impl Embedder for HttpEmbedder {
    fn model(&self) -> &str {
        &self.model
    }

    fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, String> {
        let url = format!("{}/embeddings", self.url.trim_end_matches('/'));
        let mut request = self
            .agent
            .post(&url)
            .header("Content-Type", "application/json");
        if let Some(key) = &self.api_key {
            request = request.header("Authorization", &format!("Bearer {key}"));
        }
        let body = json!({ "model": self.model, "input": texts });
        let mut response = request
            .send(body.to_string())
            .map_err(|e| format!("request to {url} failed: {e}"))?;
        let status = response.status();
        let text = response
            .body_mut()
            .read_to_string()
            .map_err(|e| format!("reading the reply failed: {e}"))?;
        if !status.is_success() {
            return Err(format!(
                "embedding endpoint answered {status}: {}",
                text.chars().take(200).collect::<String>()
            ));
        }
        let reply: Value =
            serde_json::from_str(&text).map_err(|e| format!("reply is not JSON: {e}"))?;
        let data = reply["data"].as_array().ok_or("reply has no data array")?;
        if data.len() != texts.len() {
            return Err(format!(
                "asked for {} embeddings, got {}",
                texts.len(),
                data.len()
            ));
        }
        let mut vectors = vec![Vec::new(); texts.len()];
        for (position, item) in data.iter().enumerate() {
            let index = item["index"].as_u64().map_or(position, |i| i as usize);
            let vector = item["embedding"]
                .as_array()
                .ok_or("an item has no embedding")?
                .iter()
                .map(|v| v.as_f64().map(|f| f as f32))
                .collect::<Option<Vec<f32>>>()
                .ok_or("an embedding holds a non-number")?;
            *vectors
                .get_mut(index)
                .ok_or("embedding index out of range")? = vector;
        }
        if vectors.iter().any(Vec::is_empty) {
            return Err("some texts got no embedding".into());
        }
        Ok(vectors)
    }
}

/// Embeddings already computed, by model and exact text.
pub struct EmbeddingCache {
    conn: Mutex<Connection>,
}

impl EmbeddingCache {
    /// A cache in the SQLite file at `path`, created if missing.
    pub fn open(path: impl AsRef<Path>) -> Result<EmbeddingCache, String> {
        Self::init(Connection::open(path).map_err(|e| e.to_string())?)
    }

    /// A cache that lasts as long as the process.
    pub fn in_memory() -> Result<EmbeddingCache, String> {
        Self::init(Connection::open_in_memory().map_err(|e| e.to_string())?)
    }

    fn init(conn: Connection) -> Result<EmbeddingCache, String> {
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS embeddings (
                 model  TEXT NOT NULL,
                 text   TEXT NOT NULL,
                 vector BLOB NOT NULL,
                 PRIMARY KEY (model, text)
             ) STRICT;",
        )
        .map_err(|e| e.to_string())?;
        Ok(EmbeddingCache {
            conn: Mutex::new(conn),
        })
    }

    fn get(&self, model: &str, text: &str) -> Result<Option<Vec<f32>>, String> {
        let conn = self.conn.lock().expect("cache lock");
        let blob: Option<Vec<u8>> = conn
            .query_row(
                "SELECT vector FROM embeddings WHERE model = ?1 AND text = ?2",
                params![model, text],
                |row| row.get(0),
            )
            .optional()
            .map_err(|e| e.to_string())?;
        Ok(blob.map(|bytes| {
            bytes
                .chunks_exact(4)
                .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
                .collect()
        }))
    }

    fn put(&self, model: &str, text: &str, vector: &[f32]) -> Result<(), String> {
        let bytes: Vec<u8> = vector.iter().flat_map(|f| f.to_le_bytes()).collect();
        self.conn
            .lock()
            .expect("cache lock")
            .execute(
                "INSERT OR REPLACE INTO embeddings (model, text, vector) VALUES (?1, ?2, ?3)",
                params![model, text, bytes],
            )
            .map(|_| ())
            .map_err(|e| e.to_string())
    }

    /// How many embeddings are stored.
    pub fn len(&self) -> usize {
        self.conn
            .lock()
            .expect("cache lock")
            .query_row("SELECT COUNT(*) FROM embeddings", [], |r| {
                r.get::<_, i64>(0)
            })
            .map(|n| n as usize)
            .unwrap_or(0)
    }

    /// Whether nothing is stored.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// Cosine similarity of two vectors, 0 when either is empty, zero or they differ in length.
pub fn cosine(a: &[f32], b: &[f32]) -> f64 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }
    let (mut dot, mut na, mut nb) = (0.0_f64, 0.0_f64, 0.0_f64);
    for (x, y) in a.iter().zip(b) {
        let (x, y) = (f64::from(*x), f64::from(*y));
        dot += x * y;
        na += x * x;
        nb += y * y;
    }
    if na == 0.0 || nb == 0.0 {
        return 0.0;
    }
    dot / (na.sqrt() * nb.sqrt())
}

/// How relevance is measured.
pub enum Relevance {
    /// Word overlap: deterministic, needs nothing.
    Lexical,
    /// Embeddings, with word overlap while the embedder is failing.
    Embedded {
        /// The endpoint.
        embedder: Box<dyn Embedder>,
        /// Vectors computed so far.
        cache: EmbeddingCache,
        /// Set after a failure; word overlap is used until then.
        resting_until: Mutex<Option<Instant>>,
    },
}

impl Relevance {
    /// Embedding relevance through `embedder`, remembered in `cache`.
    pub fn embedded(embedder: impl Embedder, cache: EmbeddingCache) -> Relevance {
        Relevance::Embedded {
            embedder: Box::new(embedder),
            cache,
            resting_until: Mutex::new(None),
        }
    }

    /// Relevance of every candidate in `parts` to its query, and a warning if embeddings were
    /// wanted but word overlap had to stand in.
    pub fn score(&self, parts: &PromptParts) -> (Vec<f64>, Option<String>) {
        let Relevance::Embedded {
            embedder,
            cache,
            resting_until,
        } = self
        else {
            return (parts.lexical_relevance(), None);
        };
        if resting_until
            .lock()
            .expect("rest lock")
            .is_some_and(|until| Instant::now() < until)
        {
            return (parts.lexical_relevance(), None);
        }
        match embed_all(embedder.as_ref(), cache, parts) {
            Ok(relevance) => (relevance, None),
            Err(reason) => {
                *resting_until.lock().expect("rest lock") = Some(Instant::now() + EMBEDDER_REST);
                (
                    parts.lexical_relevance(),
                    Some(format!(
                        "embeddings unavailable, using word overlap for {}s: {reason}",
                        EMBEDDER_REST.as_secs()
                    )),
                )
            }
        }
    }
}

/// Embeds the query and every candidate, asking the endpoint only for texts not in the cache.
fn embed_all(
    embedder: &dyn Embedder,
    cache: &EmbeddingCache,
    parts: &PromptParts,
) -> Result<Vec<f64>, String> {
    let model = embedder.model();
    let mut texts: Vec<&str> = vec![parts.query.as_str()];
    texts.extend(parts.candidates.iter().map(|c| c.text.as_str()));

    let mut vectors: Vec<Option<Vec<f32>>> = texts
        .iter()
        .map(|t| cache.get(model, t))
        .collect::<Result<_, _>>()?;
    let mut missing: Vec<String> = Vec::new();
    for (text, vector) in texts.iter().zip(&vectors) {
        if vector.is_none() && !missing.iter().any(|m| m == text) {
            missing.push((*text).to_owned());
        }
    }
    if !missing.is_empty() {
        let fresh = embedder.embed(&missing)?;
        for (text, vector) in missing.iter().zip(&fresh) {
            cache.put(model, text, vector)?;
        }
        for (text, slot) in texts.iter().zip(vectors.iter_mut()) {
            if slot.is_none() {
                let at = missing.iter().position(|m| m == text).expect("listed");
                *slot = Some(fresh[at].clone());
            }
        }
    }
    let query = vectors[0].take().expect("filled");
    Ok(vectors[1..]
        .iter()
        .map(|v| cosine(&query, v.as_deref().expect("filled")).max(0.0))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cosine_basics() {
        assert!((cosine(&[1.0, 0.0], &[1.0, 0.0]) - 1.0).abs() < 1e-9);
        assert!(cosine(&[1.0, 0.0], &[0.0, 1.0]).abs() < 1e-9);
        assert_eq!(cosine(&[1.0], &[1.0, 2.0]), 0.0);
        assert_eq!(cosine(&[0.0, 0.0], &[1.0, 1.0]), 0.0);
        assert_eq!(cosine(&[], &[]), 0.0);
    }

    #[test]
    fn cache_round_trips_vectors_by_model_and_text() {
        let cache = EmbeddingCache::in_memory().unwrap();
        cache.put("m1", "hello", &[0.5, -1.25, 3.0]).unwrap();
        assert_eq!(
            cache.get("m1", "hello").unwrap(),
            Some(vec![0.5, -1.25, 3.0])
        );
        assert_eq!(cache.get("m2", "hello").unwrap(), None);
        assert_eq!(cache.get("m1", "hello ").unwrap(), None);
        assert_eq!(cache.len(), 1);
    }
}
