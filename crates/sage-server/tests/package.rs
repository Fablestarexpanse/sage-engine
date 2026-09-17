//! `sage pack`, `.sagepkg` installs, hostile packages, and `sage export` round trips, against
//! the real binary.

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

fn card_bytes(greeting: &str) -> Vec<u8> {
    let card = json!({
        "spec": "chara_card_v2",
        "data": {"name": "Maren Hale", "description": "Keeps the lighthouse.", "first_mes": greeting}
    });
    sage_schema::png::with_text_chunks(&tiny_png(), &[], &[("chara", &card.to_string())]).unwrap()
}

/// A card fragment directory with a manifest stating no digest.
fn card_dir(root: &Path) -> PathBuf {
    let dir = root.join("maren");
    std::fs::create_dir_all(dir.join("assets")).unwrap();
    std::fs::write(dir.join("card.png"), card_bytes("\"Shut the door.\"")).unwrap();
    std::fs::write(dir.join("assets/notes.txt"), "made for tests").unwrap();
    std::fs::write(
        dir.join("fragment.yaml"),
        "schema: sage.fragment/1\nid: someone.maren\nkind: agent\nversion: 1.0.0\nengine: \">=0.0.1\"\n\
         title: Maren\ncreator:\n  handle: someone\nlicense: CC-BY-4.0\ncontent:\n  format: png-card\n  \
         tavern_compatible: true\n",
    )
    .unwrap();
    dir
}

#[test]
fn a_packed_fragment_installs_with_the_same_digest_as_its_directory() {
    let dir = tempfile::tempdir().unwrap();
    let fragment = card_dir(dir.path());
    let package = dir.path().join("maren.sagepkg");
    let (ok, packed, stderr) = sage(&["pack", s(&fragment), s(&package)]);
    assert!(ok, "{stderr}");
    assert_eq!(packed["fragment"], "someone.maren");

    let again = dir.path().join("again.sagepkg");
    assert!(sage(&["pack", s(&fragment), s(&again)]).0);
    assert_eq!(
        std::fs::read(&package).unwrap(),
        std::fs::read(&again).unwrap(),
        "packing is deterministic"
    );

    let (ok, from_dir, _) = sage(&["install", s(&dir.path().join("a.db")), s(&fragment)]);
    assert!(ok, "{from_dir}");
    let (ok, from_package, _) = sage(&["install", s(&dir.path().join("b.db")), s(&package)]);
    assert!(ok, "{from_package}");
    assert_eq!(from_package["digest"], from_dir["digest"]);
    assert_eq!(from_package["digest"], packed["digest"]);
    let notes = dir
        .path()
        .join("b.db.fragments/someone.maren/1.0.0/assets/notes.txt");
    assert_eq!(std::fs::read_to_string(notes).unwrap(), "made for tests");

    // The package's manifest states its digest, so it installs without that warning.
    assert!(
        !from_package["warnings"]
            .to_string()
            .contains("stated no digest"),
        "{from_package}"
    );
    let (ok, _, stderr) = sage(&[
        "install",
        s(&dir.path().join("b.db")),
        s(&package),
        "--id",
        "x.y",
    ]);
    assert!(!ok && stderr.contains("was not installed"), "{stderr}");
}

#[test]
fn a_packed_plugin_installs_after_its_checks_pass() {
    let dir = tempfile::tempdir().unwrap();
    let dialogue = sage_build::first_party_plugin("sage.dialogue");
    let package = dir.path().join("dialogue.sagepkg");
    let (ok, _, stderr) = sage(&["pack", s(&dialogue), s(&package)]);
    assert!(ok, "{stderr}");
    let (ok, report, _) = sage(&["install", s(&dir.path().join("w.db")), s(&package)]);
    assert!(ok, "{report}");
    assert_eq!(report["kind"], "plugin");

    let (ok, _, stderr) = sage(&["pack", s(&dir.path().join("missing")), s(&package)]);
    assert!(!ok && stderr.contains("was not packed"), "{stderr}");
}

/// A tar archive built by hand, so it can hold what the tar crate's builder refuses to write.
fn raw_tar(entries: &[(&str, u8, &[u8])]) -> Vec<u8> {
    let mut out = Vec::new();
    for (name, kind, data) in entries {
        let mut header = [0u8; 512];
        header[..name.len()].copy_from_slice(name.as_bytes());
        header[100..107].copy_from_slice(b"0000644");
        header[108..115].copy_from_slice(b"0000000");
        header[116..123].copy_from_slice(b"0000000");
        header[124..135].copy_from_slice(format!("{:011o}", data.len()).as_bytes());
        header[136..147].copy_from_slice(b"00000000000");
        header[156] = *kind;
        if *kind == b'2' {
            header[157..163].copy_from_slice(b"target");
        }
        header[257..263].copy_from_slice(b"ustar\0");
        header[263..265].copy_from_slice(b"00");
        header[148..156].copy_from_slice(b"        ");
        let sum: u32 = header.iter().map(|&b| u32::from(b)).sum();
        header[148..155].copy_from_slice(format!("{sum:06o}\0").as_bytes());
        out.extend_from_slice(&header);
        out.extend_from_slice(data);
        out.resize(out.len().div_ceil(512) * 512, 0);
    }
    out.resize(out.len() + 1024, 0);
    out
}

fn install_package(dir: &Path, bytes: &[u8]) -> (bool, Value) {
    let package = dir.join("hostile.sagepkg");
    std::fs::write(&package, bytes).unwrap();
    let (ok, report, _) = sage(&["install", s(&dir.join("w.db")), s(&package)]);
    (ok, report)
}

#[test]
fn hostile_packages_are_refused() {
    let dir = tempfile::tempdir().unwrap();
    let zst = |tar: &[u8]| zstd::stream::encode_all(tar, 3).unwrap();
    let manifest: &[u8] = b"schema: sage.fragment/1\n";
    let cases: Vec<(&str, Vec<u8>, &str)> = vec![
        (
            "traversal",
            zst(&raw_tar(&[
                ("fragment.yaml", b'0', manifest),
                ("../escape.txt", b'0', b"x"),
            ])),
            "not an allowed path",
        ),
        (
            "absolute",
            zst(&raw_tar(&[("/etc/escape", b'0', b"x")])),
            "not an allowed path",
        ),
        (
            "symlink",
            zst(&raw_tar(&[("link", b'2', b"")])),
            "only files and directories",
        ),
        (
            "duplicate",
            zst(&raw_tar(&[("a.txt", b'0', b"1"), ("a.txt", b'0', b"2")])),
            "appears twice",
        ),
        (
            "not zstd",
            b"PK\x03\x04 a zip file".to_vec(),
            "not a .sagepkg",
        ),
        ("empty", zst(&raw_tar(&[])), "empty"),
    ];
    for (name, bytes, expected) in cases {
        let (ok, report) = install_package(dir.path(), &bytes);
        assert!(!ok, "{name}: {report}");
        assert!(
            report["problems"].to_string().contains(expected),
            "{name}: {report}"
        );
    }
    assert!(!dir.path().join("../escape.txt").exists());

    // A compression bomb: 100 MiB of zeros compresses to a few KiB and must stop at the limit.
    let zeros = vec![0u8; 100 * 1024 * 1024];
    let bomb = zst(&raw_tar(&[("zeros.bin", b'0', &zeros)]));
    drop(zeros);
    assert!(bomb.len() < 1024 * 1024, "{}", bomb.len());
    let started = std::time::Instant::now();
    let (ok, report) = install_package(dir.path(), &bomb);
    assert!(!ok, "{report}");
    assert!(
        report["problems"].to_string().contains("at most"),
        "{report}"
    );
    assert!(started.elapsed() < std::time::Duration::from_secs(20));

    // A truncated package.
    let good = card_dir(dir.path());
    let package = dir.path().join("good.sagepkg");
    assert!(sage(&["pack", s(&good), s(&package)]).0);
    let bytes = std::fs::read(&package).unwrap();
    let (ok, report) = install_package(dir.path(), &bytes[..bytes.len() / 2]);
    assert!(!ok, "{report}");
}

#[test]
fn an_exported_sage_card_is_the_same_fragment_anywhere() {
    let dir = tempfile::tempdir().unwrap();
    let card = dir.path().join("maren.png");
    std::fs::write(&card, card_bytes("\"Shut the door.\"")).unwrap();
    let world = dir.path().join("w.db");
    let (ok, installed, _) = sage(&[
        "install",
        s(&world),
        s(&card),
        "--id",
        "someone.maren",
        "--version",
        "1.2.0",
        "--license",
        "CC-BY-4.0",
    ]);
    assert!(ok, "{installed}");

    let exported = dir.path().join("maren-sage.png");
    let (ok, report, stderr) = sage(&["export", s(&world), "someone.maren", s(&exported)]);
    assert!(ok, "{stderr}");
    assert_eq!(report["digest"], installed["digest"]);
    assert_eq!(report["tavern_compatible"], true);

    // Tavern tools still find the card; SAGE finds the manifest.
    let (ok, read, _) = sage(&["card", s(&exported)]);
    assert!(ok, "{read}");
    assert_eq!(read["source"], "chunk:chara");
    assert!(read["findings"].to_string().contains("SAGE card"), "{read}");

    let (ok, elsewhere, _) = sage(&["install", s(&dir.path().join("other.db")), s(&exported)]);
    assert!(ok, "{elsewhere}");
    assert_eq!(
        (
            &elsewhere["fragment"],
            &elsewhere["version"],
            &elsewhere["digest"]
        ),
        (
            &installed["fragment"],
            &installed["version"],
            &installed["digest"]
        )
    );
    let (ok, same, _) = sage(&["install", s(&world), s(&exported)]);
    assert!(ok, "{same}");
    assert_eq!(same["status"], "already-installed");
    let (ok, _, _) = sage(&["install", s(&world), s(&exported), "--id", "x.y"]);
    assert!(!ok, "a SAGE card carries its own manifest");

    // Editing the card inside a SAGE card breaks its digest.
    let bytes = std::fs::read(&exported).unwrap();
    let edited_card = json!({"spec": "chara_card_v2", "data": {"name": "Maren Hale", "first_mes": "\"Go away.\""}});
    let tampered = sage_schema::png::with_text_chunks(
        &bytes,
        &["chara"],
        &[("chara", &edited_card.to_string())],
    )
    .unwrap();
    let tampered_path = dir.path().join("tampered.png");
    std::fs::write(&tampered_path, tampered).unwrap();
    let (ok, report, _) = sage(&[
        "install",
        s(&dir.path().join("third.db")),
        s(&tampered_path),
    ]);
    assert!(!ok);
    assert!(
        report["problems"]
            .to_string()
            .contains("does not match its manifest"),
        "{report}"
    );

    // Only PNG agent cards export.
    let dialogue = sage_build::first_party_plugin("sage.dialogue");
    assert!(sage(&["install", s(&world), s(&dialogue)]).0);
    let (ok, _, stderr) = sage(&[
        "export",
        s(&world),
        "sage.dialogue",
        s(&dir.path().join("x.png")),
    ]);
    assert!(
        !ok && stderr.contains("only `png-card` agent fragments"),
        "{stderr}"
    );
}
