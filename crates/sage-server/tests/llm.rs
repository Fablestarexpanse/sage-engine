//! `sage run` with a model: the real binary against a stub OpenAI-compatible server. One agent
//! asks about the ferry on a schedule; a hybrid ferryman `@think`s when he hears it, and the
//! model's answer becomes his logged command.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::process::Command;
use std::sync::{Arc, Mutex};

use rusqlite::Connection;
use serde_json::{Value, json};

#[derive(Default)]
struct Seen {
    authorization: Vec<String>,
    bodies: Vec<Value>,
}

fn stub(content: &'static str) -> (String, Arc<Mutex<Seen>>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}/v1", listener.local_addr().unwrap());
    let seen = Arc::new(Mutex::new(Seen::default()));
    let record = Arc::clone(&seen);
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream) = stream else { return };
            let record = Arc::clone(&record);
            std::thread::spawn(move || {
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                let (mut length, mut authorization) = (0, String::new());
                loop {
                    let mut line = String::new();
                    if reader.read_line(&mut line).unwrap_or(0) == 0 {
                        return;
                    }
                    let line = line.trim_end().to_owned();
                    if line.is_empty() {
                        break;
                    }
                    let lower = line.to_ascii_lowercase();
                    if let Some(v) = lower.strip_prefix("content-length:") {
                        length = v.trim().parse().unwrap();
                    }
                    if lower.starts_with("authorization:") {
                        authorization = line["authorization:".len()..].trim().to_owned();
                    }
                }
                let mut body = vec![0; length];
                reader.read_exact(&mut body).unwrap();
                {
                    let mut seen = record.lock().unwrap();
                    seen.authorization.push(authorization);
                    seen.bodies.push(serde_json::from_slice(&body).unwrap());
                }
                let reply = json!({"choices": [{"message": {"content": content}}]}).to_string();
                let _ = write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{reply}",
                    reply.len()
                );
            });
        }
    });
    (url, seen)
}

fn component(name: &str, data: Value) -> (String, Value) {
    (name.to_owned(), json!({"version": 1, "data": data}))
}

fn entity(id: u64, components: Vec<(String, Value)>) -> Value {
    json!({"id": id, "components": components.into_iter().collect::<serde_json::Map<_, _>>()})
}

#[test]
fn a_hybrid_agent_answers_through_a_model_in_a_real_run() {
    let (url, seen) = stub(r#"{"command": "say Only at dawn."}"#);
    let dir = tempfile::tempdir().unwrap();
    let seed = dir.path().join("seed.json");
    let world = dir.path().join("dock.db");

    let named =
        |name: &str| component("sage.describable", json!({"name": name, "description": ""}));
    let seed_json = json!({
        "schema": "sage.seed/1",
        "entities": [
            entity(1, vec![component("sage.place", json!({})), named("Dock")]),
            entity(2, vec![
                named("Ada"),
                component("sage.actor", json!({})),
                component("sage.located", json!({"within": 1})),
                component("sage.mind", json!({
                    "driver": "scripted",
                    "think_every": 1,
                    "rules": [{"when": {"every": 25}, "do": "say Is the ferry running?"}]
                })),
            ]),
            entity(3, vec![
                named("Ferryman"),
                component("sage.actor", json!({})),
                component("sage.located", json!({"within": 1})),
                component("sage.mind", json!({
                    "driver": "hybrid",
                    "think_every": 1,
                    "persona": "A weary ferryman.",
                    "rules": [{"when": {"heard": "sage.said", "text_contains": "ferry"}, "do": "@think"}]
                })),
            ]),
        ]
    });
    std::fs::write(&seed, seed_json.to_string()).unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_sage"))
        .env("SAGE_LLM_API_KEY", "test-secret-key")
        .args(["run", world.to_str().unwrap(), "--seed"])
        .arg(&seed)
        .args([
            "--hz",
            "100",
            "--until-tick",
            "150",
            "--report-every",
            "1000",
        ])
        .args(["--llm-url", &url, "--llm-model", "stub-model"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(output.status.success(), "{stdout}\n{stderr}");
    assert!(
        stdout.contains("llm url=") && stdout.contains("model=stub-model"),
        "{stdout}"
    );
    assert!(
        !stdout.contains("test-secret-key") && !stderr.contains("test-secret-key"),
        "the API key must never be printed"
    );
    assert!(stderr.trim().is_empty(), "{stderr}");
    let stop = stdout.lines().last().unwrap();
    assert!(stop.contains(" model_failures=0"), "{stop}");

    let conn = Connection::open(&world).unwrap();
    let ferryman_commands: Vec<String> = conn
        .prepare("SELECT payload FROM events WHERE event_type = 'Occurred'")
        .unwrap()
        .query_map([], |r| r.get::<_, String>(0))
        .unwrap()
        .map(|p| serde_json::from_str::<Value>(&p.unwrap()).unwrap())
        .filter(|p| p["kind"] == "sage.command" && p["actor"] == 3)
        .map(|p| p["data"]["text"].as_str().unwrap().to_owned())
        .collect();
    assert!(!ferryman_commands.is_empty(), "the ferryman never answered");
    assert!(
        ferryman_commands.iter().all(|c| c == "say Only at dawn."),
        "{ferryman_commands:?}"
    );

    let seen = seen.lock().unwrap();
    // Every answer became a command, except possibly one asked for just before the run stopped.
    let asked = seen.bodies.len();
    assert!(
        asked == ferryman_commands.len() || asked == ferryman_commands.len() + 1,
        "{asked} requests, {} commands",
        ferryman_commands.len()
    );
    assert!(
        seen.authorization
            .iter()
            .all(|a| a == "Bearer test-secret-key")
    );
    let system = seen.bodies[0]["messages"][0]["content"].as_str().unwrap();
    assert!(system.contains("A weary ferryman."), "{system}");
    assert!(
        system.contains("emote") && system.contains("look"),
        "{system}"
    );
}
