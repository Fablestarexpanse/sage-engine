//! Playing over WebSocket against the real `sage` binary: registering, logging in, talking,
//! the limits, and accounts surviving a restart without passwords ever entering the log.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use tokio::net::TcpStream;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

type Socket = WebSocketStream<MaybeTlsStream<TcpStream>>;

struct Server {
    child: Child,
    url: String,
}

impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn seed() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../worlds/demo/seed.json")
}

/// Starts `sage run` on a free local port and waits for its `listening` line.
fn serve(world: &Path, seeded: bool) -> Server {
    serve_seed(world, seeded.then(seed))
}

fn serve_seed(world: &Path, seed: Option<PathBuf>) -> Server {
    let mut command = Command::new(env!("CARGO_BIN_EXE_sage"));
    command.args([
        "run",
        world.to_str().unwrap(),
        "--hz",
        "20",
        "--listen",
        "127.0.0.1:0",
    ]);
    if let Some(seed) = seed {
        command.arg("--seed").arg(seed);
    }
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut lines = BufReader::new(child.stdout.take().unwrap()).lines();
    let url = loop {
        let line = lines.next().expect("server exited early").unwrap();
        if let Some(rest) = line.strip_prefix("listening ") {
            break rest.split_whitespace().next().unwrap().to_owned();
        }
    };
    std::thread::spawn(move || for _ in lines {});
    Server { child, url }
}

async fn connect(server: &Server) -> Socket {
    let (mut socket, _) = tokio_tungstenite::connect_async(&server.url).await.unwrap();
    let welcome = next(&mut socket).await;
    assert_eq!(welcome["type"], "welcome");
    assert_eq!(welcome["protocol"], 1);
    socket
}

async fn send(socket: &mut Socket, frame: Value) {
    socket
        .send(Message::Text(frame.to_string().into()))
        .await
        .unwrap();
}

async fn next(socket: &mut Socket) -> Value {
    loop {
        let message = tokio::time::timeout(Duration::from_secs(10), socket.next())
            .await
            .expect("no frame within 10 s")
            .expect("connection closed")
            .unwrap();
        if let Message::Text(text) = message {
            return serde_json::from_str(text.as_str()).unwrap();
        }
    }
}

/// Reads frames until one matches, returning it; fails after 10 s.
async fn until(socket: &mut Socket, matches: impl Fn(&Value) -> bool) -> Value {
    loop {
        let frame = next(socket).await;
        if matches(&frame) {
            return frame;
        }
    }
}

fn line_text(text: &'static str) -> impl Fn(&Value) -> bool {
    move |f| f["type"] == "line" && f["text"] == text
}

async fn register(server: &Server, name: &str) -> (Socket, u64) {
    let mut socket = connect(server).await;
    send(
        &mut socket,
        json!({"type": "register", "name": name, "password": "correct horse"}),
    )
    .await;
    let session = until(&mut socket, |f| f["type"] == "session").await;
    assert_eq!(session["name"], name);
    (socket, session["character"].as_u64().unwrap())
}

#[tokio::test(flavor = "multi_thread")]
async fn two_players_register_see_each_other_and_talk() {
    let dir = tempfile::tempdir().unwrap();
    let server = serve(&dir.path().join("w.db"), true);

    let (mut ada, _) = register(&server, "Ada").await;
    let state = until(&mut ada, |f| f["type"] == "state").await;
    assert_eq!(state["place"]["name"], "First place");
    assert_eq!(state["exits"], json!(["onward"]));
    until(&mut ada, line_text("Ways on: onward.")).await;

    let (mut bo, _) = register(&server, "Bo").await;
    until(&mut bo, |f| {
        f["type"] == "line" && f["key"] == "sage.look.contents"
    })
    .await;

    send(
        &mut bo,
        json!({"type": "command", "text": "say hello, Ada"}),
    )
    .await;
    until(&mut bo, line_text("You say, \"hello, Ada\"")).await;
    let heard = until(&mut ada, line_text("Bo says, \"hello, Ada\"")).await;
    assert_eq!(heard["key"], "sage.said.other.0");
    assert_eq!(heard["params"]["actor"], "Bo");
    let state = until(&mut ada, |f| f["type"] == "state").await;
    assert!(state["here"].as_array().unwrap().contains(&json!("Bo")));

    send(&mut ada, json!({"type": "command", "text": "onward"})).await;
    until(&mut ada, line_text("You go onward.")).await;
    until(&mut bo, line_text("Ada leaves onward.")).await;
}

#[tokio::test(flavor = "multi_thread")]
async fn requests_that_break_the_rules_are_refused() {
    let dir = tempfile::tempdir().unwrap();
    let server = serve(&dir.path().join("w.db"), true);
    let mut socket = connect(&server).await;

    send(&mut socket, json!({"type": "command", "text": "look"})).await;
    assert_eq!(next(&mut socket).await["code"], "not-signed-in");

    send(
        &mut socket,
        json!({"type": "register", "name": "x", "password": "correct horse"}),
    )
    .await;
    assert_eq!(next(&mut socket).await["code"], "bad-registration");
    send(
        &mut socket,
        json!({"type": "register", "name": "Ada", "password": "short"}),
    )
    .await;
    assert_eq!(next(&mut socket).await["code"], "bad-registration");
    send(&mut socket, json!({"type": "teleport", "to": 1})).await;
    assert_eq!(next(&mut socket).await["code"], "bad-frame");

    let (_ada, _) = register(&server, "Ada").await;
    send(
        &mut socket,
        json!({"type": "register", "name": "ADA", "password": "another pass"}),
    )
    .await;
    assert_eq!(
        until(&mut socket, |f| f["type"] == "error").await["code"],
        "name-taken"
    );
    let (mut spammer, _) = register(&server, "Cy").await;
    for i in 0..8 {
        send(
            &mut spammer,
            json!({"type": "command", "text": format!("say {i}")}),
        )
        .await;
    }
    until(&mut spammer, |f| f["code"] == "slow-down").await;

    let long = "a".repeat(600);
    send(
        &mut spammer,
        json!({"type": "command", "text": format!("say {long}")}),
    )
    .await;
    until(&mut spammer, |f| f["code"] == "too-long").await;

    // A frame over 4 KiB closes the connection.
    let huge = json!({"type": "command", "text": "b".repeat(5000)}).to_string();
    let _ = spammer.send(Message::Text(huge.into())).await;
    let closed = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            match spammer.next().await {
                None | Some(Err(_)) | Some(Ok(Message::Close(_))) => return true,
                _ => {}
            }
        }
    })
    .await;
    assert_eq!(closed, Ok(true));
}

#[tokio::test(flavor = "multi_thread")]
async fn wrong_passwords_are_limited() {
    let dir = tempfile::tempdir().unwrap();
    let server = serve(&dir.path().join("w.db"), true);
    let _ = register(&server, "Ada").await;

    let mut guesser = connect(&server).await;
    for _ in 0..5 {
        send(
            &mut guesser,
            json!({"type": "login", "name": "Ada", "password": "wrong horse"}),
        )
        .await;
        assert_eq!(next(&mut guesser).await["code"], "bad-login");
    }
    let closed = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            match guesser.next().await {
                None | Some(Err(_)) | Some(Ok(Message::Close(_))) => return true,
                _ => {}
            }
        }
    })
    .await;
    assert_eq!(closed, Ok(true), "the fifth failure closes the connection");

    let mut stranger = connect(&server).await;
    send(
        &mut stranger,
        json!({"type": "login", "name": "Nobody", "password": "whatever1"}),
    )
    .await;
    assert_eq!(next(&mut stranger).await["code"], "bad-login");
}

#[tokio::test(flavor = "multi_thread")]
async fn logging_in_again_replaces_the_old_connection_and_survives_restarts() {
    let dir = tempfile::tempdir().unwrap();
    let world = dir.path().join("w.db");
    let character = {
        let server = serve(&world, true);
        let (mut first, character) = register(&server, "Ada").await;

        let mut second = connect(&server).await;
        send(
            &mut second,
            json!({"type": "login", "name": "ada", "password": "correct horse"}),
        )
        .await;
        let session = until(&mut second, |f| f["type"] == "session").await;
        assert_eq!(session["character"], character);
        assert_eq!(session["name"], "Ada");
        until(&mut first, |f| f["type"] == "kicked").await;

        send(
            &mut second,
            json!({"type": "command", "text": "say still here"}),
        )
        .await;
        until(&mut second, line_text("You say, \"still here\"")).await;
        character
    };

    let server = serve(&world, false);
    let mut again = connect(&server).await;
    send(
        &mut again,
        json!({"type": "login", "name": "Ada", "password": "correct horse"}),
    )
    .await;
    let session = until(&mut again, |f| f["type"] == "session").await;
    assert_eq!(
        session["character"], character,
        "same character after a restart"
    );
    drop(server);

    let log = rusqlite::Connection::open(&world).unwrap();
    let leaked: i64 = log
        .query_row(
            "SELECT COUNT(*) FROM events WHERE payload LIKE '%argon2%' OR payload LIKE '%correct horse%'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(leaked, 0, "passwords and hashes never enter the event log");
}

#[tokio::test(flavor = "multi_thread")]
async fn a_player_cannot_take_an_agents_name() {
    let dir = tempfile::tempdir().unwrap();
    let agents_seed =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../worlds/demo-agents/seed.json");
    let server = serve_seed(&dir.path().join("w.db"), Some(agents_seed));
    let mut socket = connect(&server).await;
    send(
        &mut socket,
        json!({"type": "register", "name": "ada", "password": "correct horse"}),
    )
    .await;
    let refused = until(&mut socket, |f| f["type"] == "error").await;
    assert_eq!(refused["code"], "name-taken");
}
