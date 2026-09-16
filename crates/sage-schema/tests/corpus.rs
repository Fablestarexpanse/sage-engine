//! Runs every manifest in `tests/corpus`. The first line of each file says what validation must
//! find: `# expect: valid`, or the sorted problem paths, with `(document)` for a whole-document
//! problem. The same corpus is used to check the WASM build gives identical reports.

use std::path::Path;

use sage_schema::{MAX_MANIFEST_BYTES, validate_manifest};

fn corpus() -> Vec<(String, String)> {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/corpus");
    let mut files: Vec<(String, String)> = std::fs::read_dir(dir)
        .unwrap()
        .map(|entry| {
            let path = entry.unwrap().path();
            let name = path.file_name().unwrap().to_string_lossy().into_owned();
            (name, std::fs::read_to_string(&path).unwrap())
        })
        .collect();
    files.sort();
    files
}

#[test]
fn corpus_matches_expectations() {
    let files = corpus();
    assert!(files.len() >= 20, "corpus went missing");
    for (name, text) in files {
        let expect = text
            .lines()
            .next()
            .and_then(|l| l.strip_prefix("# expect: "))
            .unwrap_or_else(|| panic!("{name}: first line must be `# expect: ...`"));
        let started = std::time::Instant::now();
        let report = validate_manifest(&text);
        assert!(
            started.elapsed() < std::time::Duration::from_secs(1),
            "{name}: validation took {:?}",
            started.elapsed()
        );
        if expect == "valid" {
            assert!(report.valid, "{name}: {:#?}", report.problems);
            assert!(report.manifest.is_some(), "{name}");
            continue;
        }
        assert!(!report.valid, "{name} should be invalid");
        assert!(report.manifest.is_none(), "{name}");
        let mut paths: Vec<String> = report
            .problems
            .iter()
            .map(|p| {
                if p.path.is_empty() {
                    "(document)".to_owned()
                } else {
                    p.path.clone()
                }
            })
            .collect();
        paths.sort();
        assert_eq!(paths.join(", "), expect, "{name}: {:#?}", report.problems);
        assert!(
            report.problems.iter().all(|p| !p.message.is_empty()),
            "{name}"
        );
    }
}

#[test]
fn valid_manifest_is_normalized() {
    let text = std::fs::read_to_string(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/corpus/valid-agent.yaml"),
    )
    .unwrap();
    let manifest = validate_manifest(&text).manifest.unwrap();
    assert_eq!(manifest.id.creator(), "promptwaffle");
    assert_eq!(manifest.id.slug(), "noir-detective");
    assert!(
        manifest
            .engine_requirement()
            .matches(&"0.0.1".parse().unwrap())
    );
    assert!(
        !manifest
            .engine_requirement()
            .matches(&"0.1.0".parse().unwrap())
    );
    assert_eq!(manifest.requires.len(), 2);
    assert!(manifest.requires[1].optional);
}

#[test]
fn oversized_manifest_is_refused_before_parsing() {
    let text = format!(
        "schema: sage.fragment/1\n#{}\n",
        "x".repeat(MAX_MANIFEST_BYTES)
    );
    let report = validate_manifest(&text);
    assert!(!report.valid);
    assert!(
        report.problems[0].message.contains("limit"),
        "{:?}",
        report.problems
    );
}

#[test]
fn report_json_is_stable() {
    let report = validate_manifest("schema: sage.fragment/1\nid: a.b\n");
    let json = report.to_json();
    assert!(
        json.starts_with(r#"{"valid":false,"problems":[{"path":"","message":"#),
        "{json}"
    );
    assert!(json.ends_with(r#""manifest":null}"#), "{json}");
}
