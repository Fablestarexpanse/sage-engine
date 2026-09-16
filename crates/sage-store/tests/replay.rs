//! M1 gate tests for the event log: replay determinism, restart, and what the store refuses.

use sage_core::{
    Component, ComponentRegistry, ComponentSet, Describable, EntityCreated, EntityDestroyed,
    EntityId, Event, EventLog, EventRecord, Journal, JournalError, Link, Located, Place, Scheduler,
    System, Upcasters, World,
};
use sage_store::{SqliteLog, StoreError};
use serde_json::json;

fn set<C: Component>(id: EntityId, c: &C) -> Event {
    Event::ComponentSet(ComponentSet {
        id,
        component: C::NAME.into(),
        component_version: C::VERSION,
        data: serde_json::to_value(c).unwrap(),
    })
}

fn describe(name: &str) -> Describable {
    Describable {
        name: name.into(),
        description: format!("{name}, plainly."),
    }
}

fn open(log: SqliteLog) -> Journal<SqliteLog> {
    Journal::open(log, ComponentRegistry::with_core(), Upcasters::new()).unwrap()
}

fn open_from_genesis(log: SqliteLog) -> Journal<SqliteLog> {
    Journal::open_from_genesis(log, ComponentRegistry::with_core(), Upcasters::new()).unwrap()
}

/// Small deterministic generator so the scenario is identical on every run.
struct Lcg(u64);

impl Lcg {
    fn below(&mut self, n: u64) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        (self.0 >> 33) % n
    }
}

/// Four places and 100 things, then `ticks` ticks of things moving, being renamed, and
/// occasionally being destroyed and replaced.
fn build_world(journal: &mut Journal<SqliteLog>, ticks: u64) {
    let mut places = Vec::new();
    for name in ["North", "South", "East", "West"] {
        let id = journal.world().next_entity_id();
        journal
            .commit(
                0,
                &[
                    Event::EntityCreated(EntityCreated { id }),
                    set(id, &Place {}),
                    set(id, &describe(name)),
                ],
            )
            .unwrap();
        places.push(id);
    }
    // A ring of one-way links between the places.
    for (i, from) in places.iter().enumerate() {
        let id = journal.world().next_entity_id();
        let link = Link {
            from: *from,
            to: places[(i + 1) % places.len()],
            label: "onward".into(),
        };
        journal
            .commit(
                0,
                &[Event::EntityCreated(EntityCreated { id }), set(id, &link)],
            )
            .unwrap();
    }

    let mut rng = Lcg(42);
    let mut things = Vec::new();
    for n in 0..100 {
        let id = journal.world().next_entity_id();
        let within = places[rng.below(4) as usize];
        journal
            .commit(
                0,
                &[
                    Event::EntityCreated(EntityCreated { id }),
                    set(id, &describe(&format!("thing {n}"))),
                    set(id, &Located { within }),
                ],
            )
            .unwrap();
        things.push(id);
    }

    for tick in 1..=ticks {
        let mut batch = Vec::new();
        for _ in 0..10 {
            let slot = rng.below(things.len() as u64) as usize;
            let id = things[slot];
            match rng.below(10) {
                0 => {
                    let replacement = EntityId(journal.world().next_entity_id().0);
                    batch.push(Event::EntityDestroyed(EntityDestroyed { id }));
                    journal.commit(tick, &batch).unwrap();
                    batch.clear();
                    journal
                        .commit(
                            tick,
                            &[
                                Event::EntityCreated(EntityCreated { id: replacement }),
                                set(replacement, &describe(&format!("thing @{tick}"))),
                            ],
                        )
                        .unwrap();
                    things[slot] = replacement;
                }
                1 => batch.push(set(id, &describe(&format!("renamed @{tick}")))),
                _ => {
                    let within = places[rng.below(4) as usize];
                    batch.push(set(id, &Located { within }));
                }
            }
        }
        if !batch.is_empty() {
            journal.commit(tick, &batch).unwrap();
        }
    }
}

#[test]
fn replay_from_genesis_reproduces_snapshot_bytes() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("world.db");

    let mut journal = open(SqliteLog::open(&path).unwrap());
    build_world(&mut journal, 200);
    let live = journal.world().snapshot().to_bytes();
    let live_seq = journal.world().last_seq();
    assert_eq!(journal.world().len(), 108);
    drop(journal);

    let replayed = open_from_genesis(SqliteLog::open(&path).unwrap());
    assert_eq!(replayed.world().last_seq(), live_seq);
    assert_eq!(replayed.world().snapshot().to_bytes(), live);
}

#[test]
fn snapshot_plus_tail_equals_full_replay() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("world.db");

    let mut journal = open(SqliteLog::open(&path).unwrap());
    build_world(&mut journal, 50);
    journal.save_snapshot().unwrap();
    let snapshot_seq = journal.world().last_seq();

    let id = journal.world().next_entity_id();
    journal
        .commit(
            51,
            &[
                Event::EntityCreated(EntityCreated { id }),
                set(id, &describe("after the snapshot")),
            ],
        )
        .unwrap();
    let live = journal.world().snapshot().to_bytes();
    drop(journal);

    let log = SqliteLog::open(&path).unwrap();
    assert_eq!(log.latest_snapshot().unwrap().unwrap().seq, snapshot_seq);
    let from_snapshot = open(log);
    assert_eq!(from_snapshot.world().snapshot().to_bytes(), live);
    let from_genesis = open_from_genesis(from_snapshot.into_log());
    assert_eq!(from_genesis.world().snapshot().to_bytes(), live);
    assert_eq!(
        from_genesis.world().get::<Describable>(id).unwrap().name,
        "after the snapshot"
    );
}

#[test]
fn refused_batch_writes_nothing() {
    let mut journal = open(SqliteLog::open_in_memory().unwrap());
    let id = journal.world().next_entity_id();
    journal
        .commit(0, &[Event::EntityCreated(EntityCreated { id })])
        .unwrap();
    let before = journal.world().snapshot().to_bytes();

    let missing = EntityId(999);
    let err = journal
        .commit(1, &[set(id, &Place {}), set(missing, &Place {})])
        .unwrap_err();
    assert!(matches!(err, JournalError::Refused { index: 1, .. }));
    assert_eq!(journal.world().snapshot().to_bytes(), before);
    assert_eq!(journal.log().read_from(1).unwrap().len(), 1);
}

#[test]
fn second_writer_is_refused() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("world.db");
    let mut first = open(SqliteLog::open(&path).unwrap());
    let mut second = open(SqliteLog::open(&path).unwrap());

    let id = first.world().next_entity_id();
    first
        .commit(0, &[Event::EntityCreated(EntityCreated { id })])
        .unwrap();
    let err = second
        .commit(0, &[Event::EntityCreated(EntityCreated { id })])
        .unwrap_err();
    let JournalError::Log(inner) = err else {
        panic!("expected a log error, got {err:?}");
    };
    assert!(matches!(
        inner.downcast_ref::<StoreError>(),
        Some(StoreError::SeqConflict {
            expected: 0,
            found: 1
        })
    ));
    assert!(second.world().is_empty());
}

#[test]
fn database_refuses_unversioned_event() {
    let mut log = SqliteLog::open_in_memory().unwrap();
    let record = EventRecord {
        event_type: "EntityCreated".into(),
        schema_version: 0,
        payload: json!({"id": 1}),
    };
    let err = log.append(1, 0, &[record]).unwrap_err();
    assert!(err.to_string().contains("CHECK constraint failed"), "{err}");
    assert!(log.read_from(1).unwrap().is_empty());
}

#[test]
fn database_refuses_editing_or_deleting_events() {
    let mut journal = open(SqliteLog::open_in_memory().unwrap());
    let id = journal.world().next_entity_id();
    journal
        .commit(0, &[Event::EntityCreated(EntityCreated { id })])
        .unwrap();
    let conn = journal.log().connection();
    for sql in [
        "UPDATE events SET tick = 5 WHERE seq = 1",
        "DELETE FROM events WHERE seq = 1",
    ] {
        let err = conn.execute(sql, []).unwrap_err();
        assert!(err.to_string().contains("append-only"), "{sql}: {err}");
    }
}

#[test]
fn refuses_store_from_newer_engine() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("world.db");
    SqliteLog::open(&path)
        .unwrap()
        .connection()
        .pragma_update(None, "user_version", 2)
        .unwrap();
    assert!(matches!(
        SqliteLog::open(&path),
        Err(StoreError::NewerSchema { found: 2 })
    ));
}

#[test]
fn replay_refuses_event_from_newer_engine() {
    let mut log = SqliteLog::open_in_memory().unwrap();
    let record = EventRecord {
        event_type: "EntityCreated".into(),
        schema_version: 2,
        payload: json!({"id": 1}),
    };
    log.append(1, 0, &[record]).unwrap();
    let err = Journal::open(log, ComponentRegistry::with_core(), Upcasters::new())
        .err()
        .unwrap();
    assert!(matches!(err, JournalError::Decode { seq: 1, .. }), "{err}");
}

#[test]
fn replay_refuses_log_that_does_not_apply() {
    let mut log = SqliteLog::open_in_memory().unwrap();
    let record = EventRecord {
        event_type: "EntityDestroyed".into(),
        schema_version: 1,
        payload: json!({"id": 1}),
    };
    log.append(1, 0, &[record]).unwrap();
    let err = Journal::open(log, ComponentRegistry::with_core(), Upcasters::new())
        .err()
        .unwrap();
    assert!(matches!(err, JournalError::Corrupt { seq: 1, .. }), "{err}");
}

/// Walks every entity with a `Located` one link onward every `every` ticks.
struct Wander {
    every: u64,
}

impl System for Wander {
    fn name(&self) -> &'static str {
        "wander"
    }

    fn run(&mut self, world: &World, tick: u64) -> Vec<Event> {
        if !tick.is_multiple_of(self.every) {
            return Vec::new();
        }
        (1..world.next_entity_id().0)
            .map(EntityId)
            .filter_map(|id| {
                let here = world.get::<Located>(id)?.within;
                let (_, link) = world.link_named(here, "onward")?;
                Some(set(id, &Located { within: link.to }))
            })
            .collect()
    }
}

#[test]
fn scheduled_world_replays_and_resumes_its_clock() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("world.db");

    let mut journal = open(SqliteLog::open(&path).unwrap());
    build_world(&mut journal, 0);
    let mut scheduler = Scheduler::new(&journal, 20);
    scheduler.add(Wander { every: 50 });
    let mut checkpoints = 0;
    for _ in 0..130 {
        let report = scheduler.step(&mut journal).unwrap();
        assert!(report.refused.is_empty(), "{report:?}");
        checkpoints += usize::from(report.checkpoint);
    }
    // Moves at 50 and 100; idle checkpoints at 20, 40, 70, 90, 120.
    assert_eq!(checkpoints, 5);
    assert_eq!(journal.world().tick(), 120);
    let live = journal.world().snapshot().to_bytes();
    drop(journal);

    let replayed = open_from_genesis(SqliteLog::open(&path).unwrap());
    assert_eq!(replayed.world().snapshot().to_bytes(), live);
    assert_eq!(Scheduler::new(&replayed, 20).tick(), 120);
}
