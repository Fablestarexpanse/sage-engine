//! M1 gate: a world hard-killed mid-run and restarted ends in exactly the state of a world that
//! was never interrupted.

use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::{Duration, Instant};

use rusqlite::{Connection, OpenFlags};
use sage_core::{ComponentRegistry, Journal, Upcasters};
use sage_store::SqliteLog;

const UNTIL: &str = "20000";

fn seed() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../worlds/demo/seed.json")
}

fn sage() -> Command {
    Command::new(env!("CARGO_BIN_EXE_sage"))
}

fn run_args(world: &Path) -> Vec<String> {
    [
        "run",
        world.to_str().unwrap(),
        "--hz",
        "0",
        "--until-tick",
        UNTIL,
        "--wander-every",
        "50",
        "--checkpoint-every",
        "100",
        "--snapshot-every",
        "1000",
        "--report-every",
        "1000000",
    ]
    .map(String::from)
    .to_vec()
}

fn succeed(output: Output) -> String {
    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    assert!(
        output.status.success(),
        "sage failed: {}\nstdout: {stdout}\nstderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );
    stdout
}

fn replayed_bytes(world: &Path) -> (u64, Vec<u8>) {
    let journal = Journal::open_from_genesis(
        SqliteLog::open(world).unwrap(),
        ComponentRegistry::with_core(),
        Upcasters::new(),
    )
    .unwrap();
    (
        journal.world().tick(),
        journal.world().snapshot().to_bytes(),
    )
}

/// Highest tick in the log, read without taking a write lock. None while the file is new.
fn logged_tick(world: &Path) -> Option<u64> {
    let conn = Connection::open_with_flags(world, OpenFlags::SQLITE_OPEN_READ_ONLY).ok()?;
    conn.busy_timeout(Duration::from_secs(1)).ok()?;
    conn.query_row("SELECT MAX(tick) FROM events", [], |r| {
        r.get::<_, Option<i64>>(0)
    })
    .ok()
    .flatten()
    .map(|t| t as u64)
}

#[test]
fn killed_and_resumed_world_matches_uninterrupted_world() {
    let dir = tempfile::tempdir().unwrap();

    let calm = dir.path().join("calm.db");
    let mut args = run_args(&calm);
    args.extend(["--seed".into(), seed().to_str().unwrap().into()]);
    succeed(sage().args(&args).output().unwrap());

    let killed = dir.path().join("killed.db");
    let mut args = run_args(&killed);
    args.extend(["--seed".into(), seed().to_str().unwrap().into()]);
    let mut child = sage()
        .args(&args)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let started = Instant::now();
    while logged_tick(&killed).is_none_or(|t| t < 3000) {
        assert!(
            child.try_wait().unwrap().is_none(),
            "run finished before it could be killed; raise UNTIL"
        );
        assert!(started.elapsed() < Duration::from_secs(120), "run too slow");
        std::thread::sleep(Duration::from_millis(5));
    }
    child.kill().unwrap();
    child.wait().unwrap();

    let (tick_at_kill, _) = replayed_bytes(&killed);
    assert!(
        tick_at_kill < UNTIL.parse().unwrap(),
        "kill landed after the run ended"
    );

    succeed(sage().args(run_args(&killed)).output().unwrap());

    let (calm_tick, calm_bytes) = replayed_bytes(&calm);
    let (killed_tick, killed_bytes) = replayed_bytes(&killed);
    assert_eq!(calm_tick, 20000);
    assert_eq!(killed_tick, 20000);
    assert!(
        calm_bytes == killed_bytes,
        "resumed world differs from uninterrupted world (killed at tick {tick_at_kill})"
    );

    let report = succeed(
        sage()
            .args(["inspect", killed.to_str().unwrap()])
            .output()
            .unwrap(),
    );
    assert!(
        report.contains("\"snapshot_matches_replay\":true"),
        "{report}"
    );
    assert!(report.contains("\"entities\":108"), "{report}");
}

#[test]
fn seed_is_refused_on_a_world_with_history() {
    let dir = tempfile::tempdir().unwrap();
    let world = dir.path().join("w.db");
    let seed = seed();
    let args = |until: &str| {
        [
            "run",
            world.to_str().unwrap(),
            "--seed",
            seed.to_str().unwrap(),
            "--hz",
            "0",
            "--until-tick",
            until,
        ]
        .map(String::from)
    };
    succeed(sage().args(args("5")).output().unwrap());
    let second = sage().args(args("10")).output().unwrap();
    assert!(!second.status.success());
    assert!(
        String::from_utf8_lossy(&second.stderr).contains("already has a history"),
        "{}",
        String::from_utf8_lossy(&second.stderr)
    );
}

#[test]
fn inspect_refuses_missing_file() {
    let output = sage()
        .args(["inspect", "definitely-not-here.db"])
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(!Path::new("definitely-not-here.db").exists());
}
