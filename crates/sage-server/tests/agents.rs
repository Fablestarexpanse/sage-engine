//! M3 S2 gate: ten scripted agents run for one hour of world time (14,400 ticks at 4 Hz) in
//! fast mode, with no AI, and everything they do is an ordinary logged command.

use std::collections::BTreeMap;
use std::path::Path;
use std::process::Command;

use rusqlite::Connection;

const AGENTS: std::ops::RangeInclusive<u64> = 109..=118;

#[test]
fn ten_scripted_agents_run_one_hour_of_world_time() {
    let dir = tempfile::tempdir().unwrap();
    let world = dir.path().join("agents.db");
    let seed = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../worlds/demo-agents/seed.json");
    let dialogue = sage_build::first_party_plugin("sage.dialogue");

    let started = std::time::Instant::now();
    let output = Command::new(env!("CARGO_BIN_EXE_sage"))
        .args(["run", world.to_str().unwrap(), "--seed"])
        .arg(&seed)
        .args([
            "--hz",
            "0",
            "--until-tick",
            "14400",
            "--report-every",
            "3600",
            "--plugin",
        ])
        .arg(&dialogue)
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(output.status.success(), "{stdout}\n{stderr}");
    eprintln!("{stdout}(took {:?})", started.elapsed());
    assert!(stdout.contains("agents=10"), "{stdout}");
    assert!(
        stderr.trim().is_empty(),
        "nothing refused or suspended: {stderr}"
    );
    let stop = stdout.lines().last().unwrap();
    assert!(stop.starts_with("stop tick=14400 "), "{stop}");
    assert!(stop.contains(" refused=0 "), "{stop}");

    let inspect = Command::new(env!("CARGO_BIN_EXE_sage"))
        .args(["inspect", world.to_str().unwrap()])
        .output()
        .unwrap();
    let report = String::from_utf8_lossy(&inspect.stdout);
    assert!(inspect.status.success(), "{report}");
    assert!(
        report.contains("\"snapshot_matches_replay\":true"),
        "{report}"
    );
    assert!(report.contains("\"entities\":118"), "{report}");

    // Every agent acted, only through logged commands, and the commands did things.
    let conn = Connection::open(&world).unwrap();
    let mut commands: BTreeMap<u64, usize> = BTreeMap::new();
    let mut kinds: BTreeMap<String, usize> = BTreeMap::new();
    let mut stmt = conn
        .prepare("SELECT payload FROM events WHERE event_type = 'Occurred'")
        .unwrap();
    for payload in stmt.query_map([], |row| row.get::<_, String>(0)).unwrap() {
        let payload: serde_json::Value = serde_json::from_str(&payload.unwrap()).unwrap();
        let kind = payload["kind"].as_str().unwrap().to_owned();
        if kind == "sage.command"
            && let Some(actor) = payload["actor"].as_u64()
        {
            *commands.entry(actor).or_default() += 1;
        }
        *kinds.entry(kind).or_default() += 1;
    }
    eprintln!("commands per actor: {commands:?}\noccurrences by kind: {kinds:?}");
    for agent in AGENTS {
        assert!(
            commands.get(&agent).copied().unwrap_or(0) >= 50,
            "agent {agent} barely acted: {commands:?}"
        );
    }
    assert!(
        commands.keys().all(|actor| AGENTS.contains(actor)),
        "only agents issue commands in this world: {commands:?}"
    );
    for kind in ["sage.travelled", "sage.said", "sage.emoted"] {
        assert!(
            kinds.get(kind).copied().unwrap_or(0) > 0,
            "no {kind}: {kinds:?}"
        );
    }
}
