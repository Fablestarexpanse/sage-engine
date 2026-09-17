//! `sage registry build` and `sage install --registry` against the real binary and a static
//! file server, as the Foundry's read path will be served.

use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::{Value, json};

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

fn s(path: &Path) -> &str {
    path.to_str().unwrap()
}

/// Serves the files under `root` over HTTP on a loopback port.
fn serve(root: PathBuf) -> String {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream) = stream else { continue };
            let root = root.clone();
            std::thread::spawn(move || {
                let mut line = String::new();
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                if reader.read_line(&mut line).is_err() {
                    return;
                }
                loop {
                    let mut header = String::new();
                    if reader.read_line(&mut header).is_err() || header.trim().is_empty() {
                        break;
                    }
                }
                let path = line.split_whitespace().nth(1).unwrap_or("/");
                match std::fs::read(root.join(path.trim_start_matches('/'))) {
                    Ok(body) => {
                        let _ = write!(
                            stream,
                            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                            body.len()
                        );
                        let _ = stream.write_all(&body);
                    }
                    Err(_) => {
                        let _ = write!(
                            stream,
                            "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                        );
                    }
                }
            });
        }
    });
    base
}

fn card_png(greeting: &str) -> Vec<u8> {
    use sage_schema::png;
    let mut tiny = png::SIGNATURE.to_vec();
    png::write_chunk(
        &mut tiny,
        *b"IHDR",
        &[0, 0, 0, 1, 0, 0, 0, 1, 8, 0, 0, 0, 0],
    );
    png::write_chunk(&mut tiny, *b"IEND", &[]);
    let card =
        json!({"spec": "chara_card_v2", "data": {"name": "Maren Hale", "first_mes": greeting}});
    png::with_text_chunks(&tiny, &[], &[("chara", &card.to_string())]).unwrap()
}

fn agent_dir(root: &Path, name: &str, version: &str, engine: &str, greeting: &str) -> PathBuf {
    let dir = root.join(name);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("card.png"), card_png(greeting)).unwrap();
    std::fs::write(
        dir.join("fragment.yaml"),
        format!(
            "schema: sage.fragment/1\nid: someone.maren\nkind: agent\nversion: {version}\n\
             engine: \"{engine}\"\ntitle: Maren\ncreator:\n  handle: someone\nlicense: CC-BY-4.0\n\
             content:\n  format: png-card\n  tavern_compatible: true\n"
        ),
    )
    .unwrap();
    dir
}

/// Inputs: Maren 1.0.0 as a directory, 1.1.0 as a package, 9.0.0 for an engine that does not
/// exist yet, the dialogue plugin, and three inputs that must be refused.
fn inputs(root: &Path) -> PathBuf {
    let inputs = root.join("inputs");
    std::fs::create_dir_all(&inputs).unwrap();
    agent_dir(
        &inputs,
        "maren-1.0.0",
        "1.0.0",
        ">=0.1.0",
        "\"Shut the door.\"",
    );
    let work = root.join("work");
    let v11 = agent_dir(
        &work,
        "maren-1.1.0",
        "1.1.0",
        ">=0.1.0",
        "\"Mind the stairs.\"",
    );
    assert!(sage(&["pack", s(&v11), s(&inputs.join("maren-1.1.0.sagepkg"))]).0);
    agent_dir(
        &inputs,
        "maren-9.0.0",
        "9.0.0",
        ">=99.0.0",
        "\"From the future.\"",
    );
    let dialogue = sage_build::first_party_plugin("sage.dialogue");
    let plugin = inputs.join("dialogue");
    std::fs::create_dir_all(&plugin).unwrap();
    for file in ["fragment.yaml", "plugin.wasm"] {
        std::fs::copy(dialogue.join(file), plugin.join(file)).unwrap();
    }
    std::fs::write(inputs.join("plain-card.png"), card_png("\"Hello.\"")).unwrap();
    std::fs::write(inputs.join("notes.txt"), "not a fragment").unwrap();
    agent_dir(
        &inputs,
        "maren-1.0.0-again",
        "1.0.0",
        ">=0.1.0",
        "\"Different.\"",
    );
    inputs
}

#[test]
fn a_registry_lists_what_install_would_accept_and_nothing_else() {
    let dir = tempfile::tempdir().unwrap();
    let inputs = inputs(dir.path());
    let out = dir.path().join("registry");

    let (ok, summary, stderr) = sage(&["registry", "build", s(&inputs), s(&out)]);
    assert!(!ok, "refusals fail the build: {summary}");
    assert!(stderr.contains("3 input(s) refused"), "{stderr}");
    assert_eq!(summary["fragments"], 2);
    assert_eq!(summary["versions"], 4);
    let refused: Vec<(String, String)> = summary["refused"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| {
            (
                r["source"].as_str().unwrap().to_owned(),
                r["problems"].to_string(),
            )
        })
        .collect();
    assert_eq!(refused.len(), 3, "{refused:?}");
    assert!(refused[0].0 == "maren-1.0.0-again" && refused[0].1.contains("different content"));
    assert!(refused[1].0 == "notes.txt" && refused[1].1.contains("not a .sagepkg"));
    assert!(refused[2].0 == "plain-card.png" && refused[2].1.contains("no manifest"));

    let entry: Value = serde_json::from_slice(
        &std::fs::read(out.join("api/v1/fragments/someone.maren.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(entry["schema"], "sage.registry/1");
    assert_eq!(entry["latest"], "9.0.0");
    let versions: Vec<&str> = entry["versions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v["version"].as_str().unwrap())
        .collect();
    assert_eq!(versions, ["9.0.0", "1.1.0", "1.0.0"]);
    let v10 = &entry["versions"][2];
    assert_eq!(v10["format"], "sagepkg");
    assert_eq!(v10["agent"]["name"], "Maren Hale");
    assert_eq!(v10["manifest"]["license"], "CC-BY-4.0");
    let blob = out.join(v10["url"].as_str().unwrap());
    assert_eq!(
        std::fs::metadata(&blob).unwrap().len(),
        v10["bytes"].as_u64().unwrap()
    );
    assert!(out.join("api/v1/fragments/sage.dialogue.json").exists());

    // The same inputs build the same registry, byte for byte.
    let again = dir.path().join("again");
    let _ = sage(&["registry", "build", s(&inputs), s(&again)]);
    for file in ["index.json", "api/v1/fragments/someone.maren.json"] {
        assert_eq!(
            std::fs::read(out.join(file)).unwrap(),
            std::fs::read(again.join(file)).unwrap(),
            "{file}"
        );
    }

    // Rebuilding over a registry is fine; over anything else it is refused, untouched.
    assert!(!sage(&["registry", "build", s(&inputs), s(&out)]).0);
    assert!(out.join("index.json").exists());
    let precious = dir.path().join("precious");
    std::fs::create_dir_all(&precious).unwrap();
    std::fs::write(precious.join("thesis.txt"), "do not delete").unwrap();
    let (ok, _, stderr) = sage(&["registry", "build", s(&inputs), s(&precious)]);
    assert!(!ok && stderr.contains("not a registry"), "{stderr}");
    assert!(precious.join("thesis.txt").exists());
    let (ok, _, stderr) = sage(&["registry", "build", s(&inputs), s(&inputs.join("out"))]);
    assert!(!ok && stderr.contains("must not contain"), "{stderr}");
}

#[test]
fn install_by_id_resolves_versions_and_pins_what_the_registry_listed() {
    let dir = tempfile::tempdir().unwrap();
    let inputs = inputs(dir.path());
    let out = dir.path().join("registry");
    let _ = sage(&["registry", "build", s(&inputs), s(&out)]);
    let base = serve(out.clone());
    let world = |name: &str| dir.path().join(name);

    // The newest version this engine can run: 9.0.0 needs a future engine.
    let (ok, report, _) = sage(&[
        "install",
        s(&world("a.db")),
        "someone.maren",
        "--registry",
        &base,
    ]);
    assert!(ok, "{report}");
    assert_eq!(report["version"], "1.1.0");
    assert_eq!(report["source"], format!("someone.maren@1.1.0 from {base}"));

    let (ok, report, _) = sage(&[
        "install",
        s(&world("b.db")),
        "someone.maren@=1.0.0",
        "--registry",
        &format!("{base}/"),
    ]);
    assert!(ok, "{report}");
    assert_eq!(report["version"], "1.0.0");

    let (ok, report, _) = sage(&[
        "install",
        s(&world("c.db")),
        "someone.maren@^2",
        "--registry",
        &base,
    ]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("listed: 9.0.0"),
        "{report}"
    );

    let (ok, report, _) = sage(&[
        "install",
        s(&world("c.db")),
        "nobody.here",
        "--registry",
        &base,
    ]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("not in the registry"),
        "{report}"
    );

    let (ok, report, _) = sage(&[
        "install",
        s(&world("c.db")),
        "../../etc",
        "--registry",
        &base,
    ]);
    assert!(!ok, "{report}");

    let (ok, _, _) = sage(&[
        "install",
        s(&world("c.db")),
        "someone.maren",
        "--registry",
        &base,
        "--digest",
        "sha256:00",
    ]);
    assert!(!ok);

    let entry_path = out.join("api/v1/fragments/someone.maren.json");
    let original = std::fs::read_to_string(&entry_path).unwrap();
    let mut entry: Value = serde_json::from_str(&original).unwrap();

    // A registry that lists one digest but serves other content is refused.
    entry["versions"][1]["digest"] = json!(format!("sha256:{}", "a".repeat(64)));
    std::fs::write(&entry_path, entry.to_string()).unwrap();
    let (ok, report, _) = sage(&[
        "install",
        s(&world("d.db")),
        "someone.maren",
        "--registry",
        &base,
    ]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("registry listed"),
        "{report}"
    );

    // So is one that serves another fragment's file under this id.
    let mut entry: Value = serde_json::from_str(&original).unwrap();
    let dialogue: Value = serde_json::from_slice(
        &std::fs::read(out.join("api/v1/fragments/sage.dialogue.json")).unwrap(),
    )
    .unwrap();
    entry["versions"][1]["url"] = dialogue["versions"][0]["url"].clone();
    std::fs::write(&entry_path, entry.to_string()).unwrap();
    let (ok, report, _) = sage(&[
        "install",
        s(&world("e.db")),
        "someone.maren",
        "--registry",
        &base,
    ]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("but served"),
        "{report}"
    );

    // And one whose file path leaves the registry.
    let mut entry: Value = serde_json::from_str(&original).unwrap();
    entry["versions"][1]["url"] = json!("../secrets");
    std::fs::write(&entry_path, entry.to_string()).unwrap();
    let (ok, report, _) = sage(&[
        "install",
        s(&world("f.db")),
        "someone.maren",
        "--registry",
        &base,
    ]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("outside the registry"),
        "{report}"
    );
}
