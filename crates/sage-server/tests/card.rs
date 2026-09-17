//! `sage card` against real files: a PNG card, a JSON card, and files that are not cards.

use std::path::Path;
use std::process::Command;

use serde_json::{Value, json};

fn card(path: &Path) -> (bool, Value) {
    let output = Command::new(env!("CARGO_BIN_EXE_sage"))
        .arg("card")
        .arg(path)
        .output()
        .unwrap();
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert_eq!(stdout.lines().count(), 1, "one line of JSON: {stdout}");
    (
        output.status.success(),
        serde_json::from_str(&stdout).unwrap(),
    )
}

#[test]
fn a_png_card_becomes_an_agent() {
    // The fuzzer's seed: a v2 card under `chara` and the same card as v3 under `ccv3`.
    let seed = Path::new(env!("CARGO_MANIFEST_DIR")).join("../sage-schema/fuzz/seeds/v2-v3.png");
    let (ok, report) = card(&seed);
    assert!(ok, "{report}");
    assert_eq!(report["source"], "chunk:ccv3");
    assert_eq!(report["spec"], "v3");
    assert_eq!(report["agent"]["name"], "Seed");
    assert_eq!(report["agent"]["mind"]["driver"], "hybrid");
    assert_eq!(
        report["agent"]["mind"]["persona"],
        "Seed waits.\n\nPersonality: calm"
    );
    assert_eq!(
        report["agent"]["seed_memories"],
        json!(["The door sticks."])
    );
    assert_eq!(report["agent"]["mind"]["rules"][2]["do"], "say Hello.");
}

#[test]
fn a_json_card_is_read_and_non_cards_are_refused() {
    let dir = tempfile::tempdir().unwrap();
    let json_card = dir.path().join("card.json");
    std::fs::write(
        &json_card,
        json!({"spec": "chara_card_v2", "data": {"name": "Pip", "first_mes": "Hi."}}).to_string(),
    )
    .unwrap();
    let (ok, report) = card(&json_card);
    assert!(ok, "{report}");
    assert_eq!(report["source"], "json");

    let lorebook = dir.path().join("book.json");
    std::fs::write(
        &lorebook,
        r#"{"spec": "lorebook_v3", "data": {"entries": []}}"#,
    )
    .unwrap();
    let (ok, report) = card(&lorebook);
    assert!(!ok);
    assert_eq!(report["agent"], Value::Null);
    assert_eq!(report["findings"][0]["severity"], "error");

    let gif = dir.path().join("image.png");
    std::fs::write(&gif, b"GIF89a\x01\x00\x01\x00").unwrap();
    let (ok, report) = card(&gif);
    assert!(!ok);
    assert!(
        report["findings"][0]["message"]
            .as_str()
            .unwrap()
            .contains("not a PNG file"),
        "{report}"
    );
}
