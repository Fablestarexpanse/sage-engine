//! M2 gate tests for the plugin seal and sandbox limits, run against real plugin components
//! built from `crates/sage-host/fixtures`.

use std::path::PathBuf;
use std::process::Command;
use std::sync::{Arc, OnceLock};

use sage_core::{
    ApplyError, Component, ComponentRegistry, ComponentSet, EntityCreated, EntityId, Event,
    Journal, Link, Located, Place, Scheduler, System, Upcasters, World,
};
use sage_host::{GRANTABLE, Limits, LoadError, PluginHost};
use sage_store::SqliteLog;

const ENTITIES: &str = "sage:core/entities@0.1.0";
const SPACE: &str = "sage:core/space@0.1.0";

/// Builds every fixture once per test process and returns the directory holding the `.wasm`
/// core modules.
fn fixture_dir() -> &'static PathBuf {
    static DIR: OnceLock<PathBuf> = OnceLock::new();
    DIR.get_or_init(|| {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/Cargo.toml");
        let target = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("fixtures");
        let status = Command::new(env!("CARGO"))
            .args(["build", "--release", "--target", "wasm32-unknown-unknown"])
            .arg("--manifest-path")
            .arg(&manifest)
            .arg("--target-dir")
            .arg(&target)
            .status()
            .expect("cargo runs");
        assert!(status.success(), "building fixture plugins failed");
        target.join("wasm32-unknown-unknown/release")
    })
}

/// A fixture wrapped as a component, the form plugins ship in.
fn component(name: &str) -> Vec<u8> {
    let module = std::fs::read(fixture_dir().join(format!("{name}.wasm"))).unwrap();
    wit_component::ComponentEncoder::default()
        .module(&module)
        .unwrap()
        .validate(true)
        .encode()
        .unwrap()
}

fn set<C: Component>(id: u64, c: &C) -> Event {
    Event::ComponentSet(ComponentSet {
        id: EntityId(id),
        component: C::NAME.into(),
        component_version: C::VERSION,
        data: serde_json::to_value(c).unwrap(),
    })
}

/// Places 1 and 2 joined both ways (links 3 and 4); entities 5, 6, 7 inside place 1.
fn journal() -> Journal<SqliteLog> {
    let mut journal = Journal::open(
        SqliteLog::open_in_memory().unwrap(),
        ComponentRegistry::with_core(),
        Upcasters::new(),
    )
    .unwrap();
    let mut events: Vec<Event> = (1..=7)
        .map(|id| Event::EntityCreated(EntityCreated { id: EntityId(id) }))
        .collect();
    let link = |from, to| Link {
        from: EntityId(from),
        to: EntityId(to),
        label: "onward".into(),
    };
    events.extend([
        set(1, &Place {}),
        set(2, &Place {}),
        set(3, &link(1, 2)),
        set(4, &link(2, 1)),
    ]);
    events.extend((5..=7).map(|id| {
        set(
            id,
            &Located {
                within: EntityId(1),
            },
        )
    }));
    journal.commit(0, &events).unwrap();
    journal
}

/// Native system that creates one entity every tick, to show the world keeps running.
struct Heartbeat;

impl System for Heartbeat {
    fn name(&self) -> &'static str {
        "heartbeat"
    }

    fn run(&mut self, world: &Arc<World>, _: u64) -> Result<Vec<Event>, String> {
        Ok(vec![Event::EntityCreated(EntityCreated {
            id: world.next_entity_id(),
        })])
    }
}

#[test]
fn granted_plugin_reads_the_world_and_its_events_replay_without_it() {
    let host = PluginHost::new().unwrap();
    let mut journal = journal();

    let mut mover = host
        .load(&component("mover"), &GRANTABLE, Limits::default())
        .unwrap();
    assert_eq!(mover.name(), "fixture.mover");
    let events = mover.run(journal.world_handle(), 10).unwrap();
    assert_eq!(events.len(), 3);
    let fuel = mover.last_fuel_used();
    assert!(fuel > 0 && fuel < Limits::default().fuel_per_call);
    eprintln!("mover used {fuel} fuel moving 3 entities");

    let mut scheduler = Scheduler::new(&journal, 1000);
    scheduler.add(mover);
    for _ in 0..20 {
        let report = scheduler.step(&mut journal).unwrap();
        assert!(
            report.refused.is_empty() && report.suspended.is_empty(),
            "{report:?}"
        );
    }
    // Moved at tick 10 (to place 2) and tick 20 (back to place 1).
    assert_eq!(
        journal.world().contents(EntityId(1)),
        [EntityId(5), EntityId(6), EntityId(7)]
    );
    assert_eq!(journal.world().tick(), 20);

    let live = journal.world().snapshot().to_bytes();
    let replayed = Journal::open_from_genesis(
        journal.into_log(),
        ComponentRegistry::with_core(),
        Upcasters::new(),
    )
    .unwrap();
    assert_eq!(replayed.world().snapshot().to_bytes(), live);
}

#[test]
fn plugin_importing_an_ungranted_interface_is_refused_at_load() {
    let host = PluginHost::new().unwrap();
    let err = host
        .load(&component("mover"), &[ENTITIES], Limits::default())
        .err()
        .unwrap();
    assert!(
        matches!(&err, LoadError::Ungranted { interface } if interface == SPACE),
        "{err}"
    );
    let err = host
        .load(&component("mover"), &[], Limits::default())
        .err()
        .unwrap();
    assert!(matches!(err, LoadError::Ungranted { .. }), "{err}");
}

#[test]
fn plugin_needs_no_grant_for_interfaces_it_never_imports() {
    let host = PluginHost::new().unwrap();
    let spinner = host
        .load(&component("spinner"), &[], Limits::default())
        .unwrap();
    assert_eq!(spinner.name(), "fixture.spinner");
}

#[test]
fn unknown_grant_and_invalid_bytes_are_refused() {
    let host = PluginHost::new().unwrap();
    let err = host
        .load(
            &component("spinner"),
            &["wasi:filesystem/types@0.2.0"],
            Limits::default(),
        )
        .err()
        .unwrap();
    assert!(matches!(err, LoadError::UnknownGrant(_)), "{err}");
    let err = host
        .load(b"not wasm at all", &[], Limits::default())
        .err()
        .unwrap();
    assert!(matches!(err, LoadError::Invalid(_)), "{err}");
}

/// Runs `plugin` next to [`Heartbeat`] for 5 ticks and returns the suspension reason.
fn suspended_while_world_keeps_ticking(name: &str, limits: Limits) -> String {
    let host = PluginHost::new().unwrap();
    let mut journal = journal();
    let plugin = host.load(&component(name), &GRANTABLE, limits).unwrap();
    let mut scheduler = Scheduler::new(&journal, 1000);
    scheduler.add(plugin).add(Heartbeat);
    let mut reason = None;
    for _ in 0..5 {
        let report = scheduler.step(&mut journal).unwrap();
        assert_eq!(report.committed, ["heartbeat"], "{report:?}");
        if let Some(s) = report.suspended.into_iter().next() {
            assert!(reason.is_none(), "suspended twice");
            reason = Some(s.reason);
        }
    }
    assert_eq!(journal.world().len(), 7 + 5, "heartbeat ran on every tick");
    assert_eq!(scheduler.suspended().len(), 1);
    reason.expect("plugin was suspended")
}

#[test]
fn runaway_plugin_is_stopped_by_fuel() {
    let reason = suspended_while_world_keeps_ticking("spinner", Limits::default());
    assert!(reason.contains("out of fuel"), "{reason}");
}

#[test]
fn memory_hog_is_stopped_by_the_memory_cap() {
    let limits = Limits {
        fuel_per_call: u64::MAX / 2,
        memory_bytes: 32 * 1024 * 1024,
    };
    let reason = suspended_while_world_keeps_ticking("hog", limits);
    assert_eq!(reason, "memory cap exceeded (33554432 bytes)");
}

#[test]
fn forged_events_are_refused_or_suspend_the_plugin() {
    let host = PluginHost::new().unwrap();
    let mut journal = journal();
    let forger = host
        .load(&component("forger"), &[], Limits::default())
        .unwrap();
    let mut scheduler = Scheduler::new(&journal, 1000);
    scheduler.add(forger);

    let first = scheduler.step(&mut journal).unwrap();
    assert_eq!(first.refused.len(), 1, "{first:?}");
    assert_eq!(first.refused[0].error, ApplyError::IdReused(EntityId(1)));

    let second = scheduler.step(&mut journal).unwrap();
    assert_eq!(second.suspended.len(), 1, "{second:?}");
    assert!(
        second.suspended[0].reason.contains("EverythingDeleted"),
        "{}",
        second.suspended[0].reason
    );
    assert_eq!(journal.world().len(), 7);
}
