//! A log written by an older engine keeps working. `fixtures/log-2a715f3-occurred-v1.db` was
//! recorded by engine build 2a715f3 (before `Occurred` v2 added audiences): the demo-agents
//! world with `sage.dialogue`, 600 ticks, 378 `Occurred` events at schema version 1. It is
//! never regenerated; it stands for a real world someone ran on an old build.

use std::path::{Path, PathBuf};

use sage_agents::{Agents, Memories};
use sage_core::{Event, EventLog, Journal, JournalError, Scheduler, Upcasters};
use sage_store::SqliteLog;

/// A private copy of the fixture, since opening a log may write to it.
fn fixture_copy(dir: &Path) -> PathBuf {
    let source =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/log-2a715f3-occurred-v1.db");
    let copy = dir.join("old.db");
    std::fs::copy(source, &copy).unwrap();
    copy
}

#[test]
fn old_log_replays_through_the_occurred_upcaster() {
    let dir = tempfile::tempdir().unwrap();
    let log = SqliteLog::open(fixture_copy(dir.path())).unwrap();

    let v1: Vec<_> = log
        .read_page(1, 10_000)
        .unwrap()
        .into_iter()
        .filter(|e| e.record.event_type == "Occurred")
        .collect();
    assert_eq!(v1.len(), 378);
    assert!(v1.iter().all(|e| e.record.schema_version == 1));

    let journal =
        Journal::open_from_genesis(log, sage_agents::registry(), Upcasters::core()).unwrap();
    assert_eq!(journal.world().tick(), 600);
    assert_eq!(journal.world().len(), 118);

    for stored in v1 {
        match Event::from_record(&stored.record, &Upcasters::core()).unwrap() {
            Event::Occurred(occurred) => assert!(occurred.audience.is_empty()),
            other => panic!("expected an occurrence, got {other:?}"),
        }
    }
}

#[test]
fn without_the_upcaster_the_old_log_is_refused() {
    let dir = tempfile::tempdir().unwrap();
    let log = SqliteLog::open(fixture_copy(dir.path())).unwrap();
    let err = Journal::open_from_genesis(log, sage_agents::registry(), Upcasters::new())
        .err()
        .unwrap();
    assert!(matches!(err, JournalError::Decode { .. }), "{err}");
    assert!(
        err.to_string()
            .contains("no upcaster for `Occurred` v1 -> v2"),
        "{err}"
    );
}

#[test]
fn new_engine_runs_on_top_of_the_old_log() {
    let dir = tempfile::tempdir().unwrap();
    let path = fixture_copy(dir.path());
    let mut journal = Journal::open(
        SqliteLog::open(&path).unwrap(),
        sage_agents::registry(),
        Upcasters::core(),
    )
    .unwrap();

    // Old occurrences never recorded who perceived them, so they are nobody's memory.
    let mut agents = Agents::rebuild(journal.log(), &Upcasters::core()).unwrap();
    assert_eq!(agents.memories(), &Memories::new());

    let mut scheduler = Scheduler::new(&journal, 100);
    for thought in agents.think(journal.world(), scheduler.tick() + 1) {
        scheduler.submit(thought.agent, thought.command);
    }
    for _ in 0..400 {
        let report = scheduler.step(&mut journal).unwrap();
        assert!(report.refused.is_empty() && report.suspended.is_empty());
        agents.observe(&report);
        for thought in agents.think(journal.world(), scheduler.tick() + 1) {
            scheduler.submit(thought.agent, thought.command);
        }
    }
    assert!(agents.memories().of(sage_core::EntityId(109)).count() > 0);

    let live = journal.world().snapshot().to_bytes();
    let log = journal.into_log();
    let (v1, v2) = log
        .read_page(1, 100_000)
        .unwrap()
        .into_iter()
        .filter(|e| e.record.event_type == "Occurred")
        .fold((0, 0), |(v1, v2), e| match e.record.schema_version {
            1 => (v1 + 1, v2),
            _ => (v1, v2 + 1),
        });
    assert_eq!(v1, 378, "the old events are never rewritten");
    assert!(v2 > 0);
    assert_eq!(
        Memories::rebuild(&log, &Upcasters::core()).unwrap(),
        agents.memories().clone()
    );
    let replayed =
        Journal::open_from_genesis(log, sage_agents::registry(), Upcasters::core()).unwrap();
    assert_eq!(replayed.world().snapshot().to_bytes(), live);
}
