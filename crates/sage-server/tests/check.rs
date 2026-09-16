//! `sage check` against real fragment directories: each check passes on a good fragment and
//! fails, naming the problem, on a broken one.

use std::path::Path;
use std::process::Command;

use serde_json::Value;

const ENTITIES: &str = "sage:core/entities@0.1.0";
const SPACE: &str = "sage:core/space@0.1.0";

fn manifest(id: &str, kind: &str, engine: &str, capabilities: &[&str]) -> String {
    let creator = id.split('.').next().unwrap();
    let mut text = format!(
        "schema: sage.fragment/1\nid: {id}\nkind: {kind}\nversion: 0.1.0\nengine: \"{engine}\"\n\
         title: Test fragment\ncreator:\n  handle: {creator}\nlicense: Apache-2.0\n"
    );
    if kind == "plugin" {
        text.push_str("capabilities:");
        if capabilities.is_empty() {
            text.push_str(" []\n");
        } else {
            text.push('\n');
            for c in capabilities {
                text.push_str(&format!("  - {c}\n"));
            }
        }
    }
    text
}

/// Writes a fragment directory and runs `sage check` on it. Returns (exit ok, report).
fn check(manifest: Option<&str>, plugin: Option<&str>) -> (bool, Value) {
    let dir = tempfile::tempdir().unwrap();
    if let Some(text) = manifest {
        std::fs::write(dir.path().join("fragment.yaml"), text).unwrap();
    }
    if let Some(name) = plugin {
        std::fs::write(dir.path().join("plugin.wasm"), sage_fixtures::plugin(name)).unwrap();
    }
    run_check(dir.path())
}

fn run_check(dir: &Path) -> (bool, Value) {
    let output = Command::new(env!("CARGO_BIN_EXE_sage"))
        .arg("check")
        .arg(dir)
        .output()
        .unwrap();
    let stdout = String::from_utf8(output.stdout).unwrap();
    let report: Value = serde_json::from_str(stdout.trim())
        .unwrap_or_else(|e| panic!("report is not JSON ({e}): {stdout}"));
    assert_eq!(output.status.success(), report["ok"] == true, "{report}");
    (output.status.success(), report)
}

/// `(check, status)` pairs, and every problem joined, for compact assertions.
fn summary(report: &Value) -> (Vec<(String, String)>, String) {
    let checks = report["checks"].as_array().unwrap();
    let statuses = checks
        .iter()
        .map(|c| {
            (
                c["check"].as_str().unwrap().to_owned(),
                c["status"].as_str().unwrap().to_owned(),
            )
        })
        .collect();
    let problems = checks
        .iter()
        .flat_map(|c| c["problems"].as_array().unwrap().iter())
        .map(|p| p.as_str().unwrap().to_owned())
        .collect::<Vec<_>>()
        .join(" | ");
    (statuses, problems)
}

fn statuses(pairs: &[(&str, &str)]) -> Vec<(String, String)> {
    pairs
        .iter()
        .map(|(a, b)| ((*a).to_owned(), (*b).to_owned()))
        .collect()
}

#[test]
fn good_plugin_passes_every_check() {
    let (ok, report) = check(
        Some(&manifest(
            "fixture.mover",
            "plugin",
            "^0.0.1",
            &[ENTITIES, SPACE],
        )),
        Some("mover"),
    );
    assert!(ok, "{report}");
    assert_eq!(report["fragment"], "fixture.mover");
    assert_eq!(report["engine"], env!("CARGO_PKG_VERSION"));
    let (s, _) = summary(&report);
    assert_eq!(
        s,
        statuses(&[
            ("manifest", "pass"),
            ("engine", "pass"),
            ("capabilities", "pass"),
            ("boot", "pass")
        ])
    );
}

#[test]
fn content_fragment_skips_plugin_checks() {
    let (ok, report) = check(
        Some(&manifest("someone.old-map", "place", "^0.0.1", &[])),
        None,
    );
    assert!(ok, "{report}");
    let (s, _) = summary(&report);
    assert_eq!(
        s,
        statuses(&[
            ("manifest", "pass"),
            ("engine", "pass"),
            ("capabilities", "skipped"),
            ("boot", "skipped")
        ])
    );
}

#[test]
fn undeclared_import_fails_capabilities() {
    let (ok, report) = check(
        Some(&manifest("fixture.mover", "plugin", "^0.0.1", &[ENTITIES])),
        Some("mover"),
    );
    assert!(!ok);
    let (s, problems) = summary(&report);
    assert_eq!(s[2], ("capabilities".into(), "fail".into()));
    assert_eq!(s[3], ("boot".into(), "skipped".into()));
    assert!(
        problems.contains("imports `sage:core/space@0.1.0` but does not declare it"),
        "{problems}"
    );
}

#[test]
fn unserved_and_unused_capabilities_fail() {
    let (ok, report) = check(
        Some(&manifest(
            "fixture.spinner",
            "plugin",
            "^0.0.1",
            &["sage:core/clock@0.1.0", ENTITIES],
        )),
        Some("spinner"),
    );
    assert!(!ok);
    let (_, problems) = summary(&report);
    assert!(
        problems.contains("`sage:core/clock@0.1.0`, which this engine does not serve"),
        "{problems}"
    );
    assert!(
        problems.contains("declares `sage:core/entities@0.1.0` but never imports it"),
        "{problems}"
    );
}

#[test]
fn name_mismatch_and_runaway_plugin_fail_boot() {
    let (ok, report) = check(
        Some(&manifest("fixture.walker", "plugin", "^0.0.1", &[])),
        Some("spinner"),
    );
    assert!(!ok);
    let (s, problems) = summary(&report);
    assert_eq!(s[3], ("boot".into(), "fail".into()));
    assert!(
        problems.contains("names itself `fixture.spinner` but the manifest id is `fixture.walker`"),
        "{problems}"
    );
    assert!(problems.contains("out of fuel"), "{problems}");
}

#[test]
fn wrong_engine_fails_but_other_checks_still_run() {
    let (ok, report) = check(
        Some(&manifest(
            "fixture.mover",
            "plugin",
            "^9",
            &[ENTITIES, SPACE],
        )),
        Some("mover"),
    );
    assert!(!ok);
    let (s, problems) = summary(&report);
    assert_eq!(
        s,
        statuses(&[
            ("manifest", "pass"),
            ("engine", "fail"),
            ("capabilities", "pass"),
            ("boot", "pass")
        ])
    );
    assert!(problems.contains("requires engine `^9`"), "{problems}");
}

#[test]
fn bad_or_missing_manifest_skips_everything_else() {
    for text in [None, Some("schema: sage.fragment/1\nid: Bad Id\n")] {
        let (ok, report) = check(text, Some("mover"));
        assert!(!ok);
        assert!(report["fragment"].is_null(), "{report}");
        let (s, problems) = summary(&report);
        assert_eq!(
            s,
            statuses(&[
                ("manifest", "fail"),
                ("engine", "skipped"),
                ("capabilities", "skipped"),
                ("boot", "skipped")
            ]),
            "{problems}"
        );
    }
}

#[test]
fn plugin_without_wasm_fails_capabilities() {
    let (ok, report) = check(
        Some(&manifest(
            "fixture.mover",
            "plugin",
            "^0.0.1",
            &[ENTITIES, SPACE],
        )),
        None,
    );
    assert!(!ok);
    let (s, problems) = summary(&report);
    assert_eq!(s[2], ("capabilities".into(), "fail".into()));
    assert!(problems.contains("plugin.wasm"), "{problems}");
}
