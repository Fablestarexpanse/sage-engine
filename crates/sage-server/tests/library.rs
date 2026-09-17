//! `sage install` and `sage place` against the real binary: cards and plugins into a world's
//! library, what is refused, and an installed agent answering a player in a running world.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use tokio_tungstenite::tungstenite::Message;

fn sage(args: &[&str]) -> (bool, Value, String) {
    let output = Command::new(env!("CARGO_BIN_EXE_sage"))
        .args(args)
        .output()
        .unwrap();
    let stdout = String::from_utf8(output.stdout).unwrap();
    let stderr = String::from_utf8(output.stderr).unwrap();
    let report = stdout
        .lines()
        .last()
        .and_then(|l| serde_json::from_str(l).ok())
        .unwrap_or(Value::Null);
    (output.status.success(), report, stderr)
}

fn tiny_png() -> Vec<u8> {
    use sage_schema::png;
    let mut out = png::SIGNATURE.to_vec();
    png::write_chunk(&mut out, *b"IHDR", &[0, 0, 0, 1, 0, 0, 0, 1, 8, 0, 0, 0, 0]);
    png::write_chunk(
        &mut out,
        *b"IDAT",
        &[0x78, 0x9c, 0x63, 0x60, 0x00, 0x00, 0x00, 0x02, 0x00, 0x01],
    );
    png::write_chunk(&mut out, *b"IEND", &[]);
    out
}

/// A card PNG with the card as plain JSON in `chara` (read with a note, as some tools write it).
fn card_png(dir: &Path, file: &str, first_mes: &str) -> PathBuf {
    let card = json!({
        "spec": "chara_card_v2",
        "data": {
            "name": "Maren Hale",
            "description": "{{char}} keeps the lighthouse.",
            "personality": "dry",
            "first_mes": first_mes,
            "character_book": {"entries": [
                {"keys": ["lamp"], "content": "The lamp has not failed in forty years.", "enabled": true}
            ]}
        }
    });
    let png = sage_schema::png::with_text_chunks(&tiny_png(), &[], &[("chara", &card.to_string())])
        .unwrap();
    let path = dir.join(file);
    std::fs::write(&path, png).unwrap();
    path
}

fn seeded_world(dir: &Path) -> PathBuf {
    let world = dir.join("w.db");
    let seed = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../worlds/demo/seed.json");
    let output = Command::new(env!("CARGO_BIN_EXE_sage"))
        .args(["run", world.to_str().unwrap(), "--seed"])
        .arg(&seed)
        .args(["--hz", "0", "--until-tick", "2"])
        .output()
        .unwrap();
    assert!(output.status.success());
    world
}

fn s(path: &Path) -> &str {
    path.to_str().unwrap()
}

#[test]
fn cards_install_once_and_changed_content_needs_a_new_version() {
    let dir = tempfile::tempdir().unwrap();
    let world = dir.path().join("w.db");
    let card = card_png(dir.path(), "maren.png", "\"Shut the door.\"");

    let (ok, report, _) = sage(&["install", s(&world), s(&card)]);
    assert!(ok, "{report}");
    assert_eq!(report["status"], "installed");
    assert_eq!(report["fragment"], "local.maren-hale");
    assert_eq!(report["version"], "0.1.0");
    assert_eq!(report["kind"], "agent");
    let warnings = report["warnings"].to_string();
    for expected in ["installed as 0.1.0", "LicenseRef-Unspecified", "unsigned"] {
        assert!(warnings.contains(expected), "{expected}: {warnings}");
    }
    let installed = dir.path().join("w.db.fragments/local.maren-hale/0.1.0");
    assert_eq!(
        std::fs::read(installed.join("card.png")).unwrap(),
        std::fs::read(&card).unwrap()
    );
    let manifest = std::fs::read_to_string(installed.join("fragment.yaml")).unwrap();
    assert!(
        manifest.contains(report["digest"].as_str().unwrap()),
        "{manifest}"
    );

    let (ok, again, _) = sage(&["install", s(&world), s(&card)]);
    assert!(ok, "{again}");
    assert_eq!(again["status"], "already-installed");

    let changed = card_png(dir.path(), "maren2.png", "\"Mind the stairs.\"");
    let (ok, refused, _) = sage(&["install", s(&world), s(&changed)]);
    assert!(!ok);
    assert!(
        refused["problems"][0]
            .as_str()
            .unwrap()
            .contains("different content"),
        "{refused}"
    );
    let (ok, bumped, _) = sage(&[
        "install",
        s(&world),
        s(&changed),
        "--version",
        "0.2.0",
        "--license",
        "CC-BY-4.0",
        "--id",
        "someone.maren",
    ]);
    assert!(ok, "{bumped}");
    assert_eq!(bumped["fragment"], "someone.maren");

    // No world is created by installing.
    assert!(!world.exists());

    let not_a_card = dir.path().join("notes.json");
    std::fs::write(
        &not_a_card,
        r#"{"spec": "lorebook_v3", "data": {"entries": []}}"#,
    )
    .unwrap();
    let (ok, report, _) = sage(&["install", s(&world), s(&not_a_card)]);
    assert!(!ok);
    assert!(
        report["problems"][0].as_str().unwrap().contains("lorebook"),
        "{report}"
    );
}

#[test]
fn fragment_directories_are_checked_against_their_digest() {
    let dir = tempfile::tempdir().unwrap();
    let world = dir.path().join("w.db");
    let card = card_png(dir.path(), "card.png", "\"Hello.\"");
    let fragment = dir.path().join("fragment");
    std::fs::create_dir(&fragment).unwrap();
    std::fs::copy(&card, fragment.join("card.png")).unwrap();
    let manifest = |digest: &str| {
        format!(
            "schema: sage.fragment/1\nid: someone.maren\nkind: agent\nversion: 1.0.0\nengine: \">=0.0.1\"\n\
             title: Maren\ncreator:\n  handle: someone\nlicense: CC-BY-4.0\ncontent:\n  format: png-card\n  \
             tavern_compatible: true\nintegrity:\n  digest: \"{digest}\"\n"
        )
    };
    let wrong = format!("sha256:{}", "0".repeat(64));
    std::fs::write(fragment.join("fragment.yaml"), manifest(&wrong)).unwrap();
    let (ok, report, _) = sage(&["install", s(&world), s(&fragment)]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("does not match its manifest"),
        "{report}"
    );

    let right =
        sage_schema::digest::content_digest(&[("card.png", &std::fs::read(&card).unwrap())])
            .unwrap();
    std::fs::write(fragment.join("fragment.yaml"), manifest(&right)).unwrap();
    let (ok, report, _) = sage(&["install", s(&world), s(&fragment)]);
    assert!(ok, "{report}");
    assert_eq!(report["digest"], right.as_str());
    assert_eq!(
        report["warnings"],
        json!(["unsigned: accepted on its content digest alone"])
    );

    // Card options make no sense for a directory, which has its own manifest.
    let (ok, _, _) = sage(&["install", s(&world), s(&fragment), "--id", "x.y"]);
    assert!(!ok);

    // Kinds the engine cannot use yet are refused.
    std::fs::write(
        fragment.join("fragment.yaml"),
        manifest(&right).replace("kind: agent", "kind: quest"),
    )
    .unwrap();
    let (ok, report, _) = sage(&["install", s(&world), s(&fragment)]);
    assert!(!ok, "{report}");
}

#[test]
fn plugins_install_only_when_sage_check_passes() {
    let dir = tempfile::tempdir().unwrap();
    let world = dir.path().join("w.db");
    let dialogue = sage_build::first_party_plugin("sage.dialogue");
    let (ok, report, _) = sage(&["install", s(&world), s(&dialogue)]);
    assert!(ok, "{report}");
    assert_eq!(report["kind"], "plugin");
    assert!(
        dir.path()
            .join("w.db.fragments/sage.dialogue")
            .read_dir()
            .unwrap()
            .count()
            == 1
    );

    // The same plugin with an undeclared capability removed fails its checks.
    let broken = dir.path().join("broken");
    std::fs::create_dir(&broken).unwrap();
    std::fs::copy(dialogue.join("plugin.wasm"), broken.join("plugin.wasm")).unwrap();
    let text = std::fs::read_to_string(dialogue.join("fragment.yaml")).unwrap();
    let without: String = text
        .lines()
        .filter(|l| !l.contains("sage:core/space"))
        .map(|l| format!("{l}\n"))
        .collect();
    assert_ne!(
        text.lines().count(),
        without.lines().count(),
        "fixture changed: {text}"
    );
    std::fs::write(broken.join("fragment.yaml"), without).unwrap();
    let (ok, report, _) = sage(&["install", s(&world), s(&broken)]);
    assert!(!ok, "{report}");
    assert!(
        report["problems"].to_string().contains("sage check"),
        "{report}"
    );
}

#[test]
fn placing_refuses_tampered_fragments_taken_names_and_non_places() {
    let dir = tempfile::tempdir().unwrap();
    let world = seeded_world(dir.path());
    let card = card_png(dir.path(), "maren.png", "\"Shut the door.\"");
    assert!(sage(&["install", s(&world), s(&card)]).0);

    let (ok, report, stderr) = sage(&["place", s(&world), "local.maren-hale", "--at", "999"]);
    assert!(!ok && report.is_null(), "{report}");
    assert!(stderr.contains("not a place"), "{stderr}");

    let (ok, report, stderr) = sage(&["place", s(&world), "local.maren-hale"]);
    assert!(ok, "{stderr}");
    assert_eq!(report["name"], "Maren Hale");
    assert_eq!(report["memories"], 1);
    assert_eq!(report["place"], 1);

    let (ok, _, stderr) = sage(&["place", s(&world), "local.maren-hale@0.1.0"]);
    assert!(!ok);
    assert!(stderr.contains("already in this world"), "{stderr}");
    let (ok, second, stderr) = sage(&[
        "place",
        s(&world),
        "local.maren-hale",
        "--name",
        "Maren Two",
    ]);
    assert!(ok, "{stderr}");
    assert_eq!(second["entity"], report["entity"].as_u64().unwrap() + 1);

    let (ok, _, stderr) = sage(&["place", s(&world), "local.nobody"]);
    assert!(!ok && stderr.contains("not installed"), "{stderr}");
    let (ok, _, stderr) = sage(&["place", s(&world), "local.maren-hale@9.9.9"]);
    assert!(!ok && stderr.contains("not installed"), "{stderr}");

    // Changing an installed file is caught before anything reaches the world.
    let installed = dir
        .path()
        .join("w.db.fragments/local.maren-hale/0.1.0/card.png");
    let mut bytes = std::fs::read(&installed).unwrap();
    bytes.push(0);
    std::fs::write(&installed, bytes).unwrap();
    let (ok, _, stderr) = sage(&[
        "place",
        s(&world),
        "local.maren-hale",
        "--name",
        "Maren Three",
    ]);
    assert!(!ok);
    assert!(stderr.contains("changed after install"), "{stderr}");

    let inspect = Command::new(env!("CARGO_BIN_EXE_sage"))
        .args(["inspect", s(&world)])
        .output()
        .unwrap();
    let inspected = String::from_utf8(inspect.stdout).unwrap();
    assert!(
        inspected.contains("\"snapshot_matches_replay\":true"),
        "{inspected}"
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn a_placed_agent_answers_a_player_and_the_running_world_refuses_a_second_writer() {
    let dir = tempfile::tempdir().unwrap();
    let world = seeded_world(dir.path());
    let card = card_png(dir.path(), "maren.png", "*looks up* \"Shut the door.\"");
    assert!(sage(&["install", s(&world), s(&card)]).0);
    let (ok, _, stderr) = sage(&["place", s(&world), "local.maren-hale"]);
    assert!(ok, "{stderr}");

    let mut child = Command::new(env!("CARGO_BIN_EXE_sage"))
        .args(["run", s(&world), "--hz", "20", "--listen", "127.0.0.1:0"])
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

    // While the world runs, placing is refused rather than writing beside it.
    let (ok, _, stderr) = sage(&["place", s(&world), "local.maren-hale", "--name", "Other"]);
    assert!(!ok, "a second writer must be refused");
    assert!(
        stderr.contains("in use by another sage process"),
        "{stderr}"
    );
    let (ok, _, stderr) = sage(&["run", s(&world), "--until-tick", "1"]);
    assert!(!ok && stderr.contains("in use"), "{stderr}");

    let (mut socket, _) = tokio_tungstenite::connect_async(&url).await.unwrap();
    let send = |text: Value| Message::Text(text.to_string().into());
    socket
        .send(send(
            json!({"type": "register", "name": "Bo", "password": "correct horse"}),
        ))
        .await
        .unwrap();
    socket
        .send(send(
            json!({"type": "command", "text": "say Maren, is the lamp lit?"}),
        ))
        .await
        .unwrap();
    let mut heard = Vec::new();
    let answer = tokio::time::timeout(Duration::from_secs(20), async {
        while let Some(Ok(message)) = socket.next().await {
            if let Message::Text(text) = message {
                let frame: Value = serde_json::from_str(text.as_str()).unwrap();
                if frame["type"] == "line" {
                    let line = frame["text"].as_str().unwrap_or_default().to_owned();
                    heard.push(line.clone());
                    if line.starts_with("Maren Hale says") {
                        return line;
                    }
                }
            }
        }
        panic!("closed");
    })
    .await
    .unwrap_or_else(|_| panic!("no answer; heard {heard:?}"));
    assert_eq!(answer, "Maren Hale says, \"Shut the door.\"");
    assert!(
        heard.iter().all(|l| !l.contains("forty years")),
        "a seed memory is the agent's alone: {heard:?}"
    );
    let _ = child.kill();
    let _ = child.wait();
}
