//! `sage install <world> <url>` against a local HTTP server: pinned digests, failures, and
//! downloads that never end.

use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::Path;
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

/// Serves `/maren.sagepkg`, `/missing` (404) and `/endless` (a body that never ends) until
/// the test ends. Returns the base URL.
fn serve(package: Vec<u8>) -> String {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream) = stream else { continue };
            let package = package.clone();
            std::thread::spawn(move || {
                let mut request_line = String::new();
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                if reader.read_line(&mut request_line).is_err() {
                    return;
                }
                loop {
                    let mut header = String::new();
                    if reader.read_line(&mut header).is_err() || header.trim().is_empty() {
                        break;
                    }
                }
                let path = request_line.split_whitespace().nth(1).unwrap_or("/");
                match path {
                    "/maren.sagepkg" => {
                        let _ = write!(
                            stream,
                            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                            package.len()
                        );
                        let _ = stream.write_all(&package);
                    }
                    "/endless" => {
                        let _ = write!(
                            stream,
                            "HTTP/1.1 200 OK\r\nContent-Length: 1000000000\r\nConnection: close\r\n\r\n"
                        );
                        let chunk = vec![0u8; 1024 * 1024];
                        while stream.write_all(&chunk).is_ok() {}
                    }
                    _ => {
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

fn package(dir: &Path) -> (Vec<u8>, String) {
    use sage_schema::png;
    let mut tiny = png::SIGNATURE.to_vec();
    png::write_chunk(
        &mut tiny,
        *b"IHDR",
        &[0, 0, 0, 1, 0, 0, 0, 1, 8, 0, 0, 0, 0],
    );
    png::write_chunk(&mut tiny, *b"IEND", &[]);
    let card =
        json!({"spec": "chara_card_v2", "data": {"name": "Maren Hale", "first_mes": "\"Hello.\""}});
    let card = png::with_text_chunks(&tiny, &[], &[("chara", &card.to_string())]).unwrap();
    let fragment = dir.join("maren");
    std::fs::create_dir_all(&fragment).unwrap();
    std::fs::write(fragment.join("card.png"), card).unwrap();
    std::fs::write(
        fragment.join("fragment.yaml"),
        "schema: sage.fragment/1\nid: someone.maren\nkind: agent\nversion: 1.0.0\nengine: \">=0.0.1\"\n\
         title: Maren\ncreator:\n  handle: someone\nlicense: CC-BY-4.0\ncontent:\n  format: png-card\n  \
         tavern_compatible: true\n",
    )
    .unwrap();
    let out = dir.join("maren.sagepkg");
    let (ok, packed, stderr) = sage(&["pack", s(&fragment), s(&out)]);
    assert!(ok, "{stderr}");
    (
        std::fs::read(out).unwrap(),
        packed["digest"].as_str().unwrap().to_owned(),
    )
}

#[test]
fn a_fragment_installs_from_a_url_pinned_by_its_digest() {
    let dir = tempfile::tempdir().unwrap();
    let (bytes, digest) = package(dir.path());
    let base = serve(bytes);
    let url = format!("{base}/maren.sagepkg");
    let world = dir.path().join("w.db");

    let wrong = format!("sha256:{}", "1".repeat(64));
    let (ok, report, _) = sage(&["install", s(&world), &url, "--digest", &wrong]);
    assert!(!ok, "{report}");
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("not the expected"),
        "{report}"
    );
    assert!(!dir.path().join("w.db.fragments/someone.maren").exists());

    let (ok, report, _) = sage(&["install", s(&world), &url, "--digest", &digest]);
    assert!(ok, "{report}");
    assert_eq!(report["source"], url.as_str());
    assert_eq!(report["digest"], digest.as_str());
    assert!(
        !report["warnings"].to_string().contains("without --digest"),
        "{report}"
    );

    let (ok, report, _) = sage(&["install", s(&dir.path().join("x.db")), &url]);
    assert!(ok, "{report}");
    assert!(
        report["warnings"].to_string().contains("without --digest"),
        "{report}"
    );

    // --digest pins local files too.
    let local = dir.path().join("maren.sagepkg");
    let (ok, _, _) = sage(&[
        "install",
        s(&dir.path().join("y.db")),
        s(&local),
        "--digest",
        &wrong,
    ]);
    assert!(!ok);
}

#[test]
fn failed_and_oversized_downloads_are_refused() {
    let dir = tempfile::tempdir().unwrap();
    let base = serve(Vec::new());
    let world = dir.path().join("w.db");

    let (ok, report, _) = sage(&["install", s(&world), &format!("{base}/missing")]);
    assert!(!ok);
    assert!(
        report["problems"][0].as_str().unwrap().contains("404"),
        "{report}"
    );

    let started = std::time::Instant::now();
    let (ok, report, _) = sage(&["install", s(&world), &format!("{base}/endless")]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("at most 64 MiB"),
        "{report}"
    );
    assert!(started.elapsed() < std::time::Duration::from_secs(60));

    let (ok, report, _) = sage(&["install", s(&world), "http://example.invalid/a.sagepkg"]);
    assert!(!ok);
    assert!(
        report["problems"][0]
            .as_str()
            .unwrap()
            .contains("only https"),
        "{report}"
    );
    assert!(!world.exists());
}
