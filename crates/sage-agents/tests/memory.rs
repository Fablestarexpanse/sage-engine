//! Memory is a projection of the log: live memory equals memory rebuilt from the log, and a
//! world restarted over and over behaves exactly like one that never stopped.

use sage_agents::{Agents, Memories, Mind, Rule, When};
use sage_core::{
    Actor, Component, ComponentSet, Describable, EntityCreated, EntityId, Event, Journal, Link,
    Located, Place, Scheduler, Upcasters,
};
use sage_store::SqliteLog;

fn set<C: Component>(id: u64, c: &C) -> Event {
    Event::ComponentSet(ComponentSet {
        id: EntityId(id),
        component: C::NAME.into(),
        component_version: C::VERSION,
        data: serde_json::to_value(c).unwrap(),
    })
}

/// Two places; four chatty agents (ids 5-8) who greet often and answer greetings, so what an
/// agent heard in its last few ticks almost always decides what it does next.
fn seed(journal: &mut Journal<SqliteLog>) {
    let mut events: Vec<Event> = (1..=8)
        .map(|id| Event::EntityCreated(EntityCreated { id: EntityId(id) }))
        .collect();
    let named = |name: &str| Describable {
        name: name.into(),
        description: String::new(),
    };
    events.extend([
        set(1, &Place {}),
        set(1, &named("Hall")),
        set(2, &Place {}),
        set(2, &named("Yard")),
        set(
            3,
            &Link {
                from: EntityId(1),
                to: EntityId(2),
                label: "out".into(),
            },
        ),
        set(
            4,
            &Link {
                from: EntityId(2),
                to: EntityId(1),
                label: "in".into(),
            },
        ),
    ]);
    for (id, name) in [(5, "Ada"), (6, "Bo"), (7, "Cy"), (8, "Dee")] {
        let mind = Mind {
            driver: "scripted".into(),
            think_every: 3 + id % 3,
            persona: String::new(),
            goals: vec![],
            rules: vec![
                Rule {
                    when: When {
                        heard: Some("sage.said".into()),
                        text_contains: Some("good day".into()),
                        ..When::default()
                    },
                    command: "say Well met, {speaker}.".into(),
                },
                Rule {
                    when: When {
                        heard: Some("sage.said".into()),
                        text_contains: Some("well met".into()),
                        chance: Some(0.5),
                        ..When::default()
                    },
                    command: "go {any_exit}".into(),
                },
                Rule {
                    when: When {
                        chance: Some(0.3),
                        alone: Some(false),
                        ..When::default()
                    },
                    command: "say Good day, {any_actor}.".into(),
                },
            ],
            importance: Default::default(),
            reflect_threshold: None,
        };
        events.extend([
            set(id, &named(name)),
            set(id, &Actor {}),
            set(
                id,
                &Located {
                    within: EntityId(1),
                },
            ),
            set(id, &mind),
        ]);
    }
    journal.commit(0, &events).unwrap();
}

fn open(log: SqliteLog) -> Journal<SqliteLog> {
    Journal::open(log, sage_agents::registry(), Upcasters::core()).unwrap()
}

/// Runs to `until`, doing what `sage run` does on start: rebuild memory, think for the next
/// tick, then step. Restarts (drops everything but the log) every `restart_every` ticks.
fn run(until: u64, restart_every: Option<u64>) -> (SqliteLog, Agents) {
    let mut journal = open(SqliteLog::open_in_memory().unwrap());
    seed(&mut journal);
    let start = |journal: &Journal<SqliteLog>| {
        let mut scheduler = Scheduler::new(journal, u64::MAX);
        let mut agents = Agents::rebuild(journal.log(), &Upcasters::core()).unwrap();
        for thought in agents.think(journal.world(), scheduler.tick() + 1) {
            scheduler.submit(thought.agent, thought.command);
        }
        (scheduler, agents)
    };
    let (mut scheduler, mut agents) = start(&journal);
    let mut steps = 0;
    while scheduler.tick() < until {
        let report = scheduler.step(&mut journal).unwrap();
        agents.observe(&report);
        for thought in agents.think(journal.world(), scheduler.tick() + 1) {
            scheduler.submit(thought.agent, thought.command);
        }
        steps += 1;
        if restart_every.is_some_and(|every| steps % every == 0) {
            journal = open(journal.into_log());
            (scheduler, agents) = start(&journal);
        }
    }
    (journal.into_log(), agents)
}

fn non_clock_events(log: &SqliteLog) -> Vec<(u64, String)> {
    use sage_core::EventLog;
    log.read_page(1, 1_000_000)
        .unwrap()
        .into_iter()
        .filter(|e| e.record.event_type != "ClockAdvanced")
        .map(|e| (e.tick, e.record.payload.to_string()))
        .collect()
}

#[test]
fn live_memory_equals_memory_rebuilt_from_the_log() {
    let (log, agents) = run(400, None);
    let rebuilt = Memories::rebuild(&log, &Upcasters::core()).unwrap();
    assert_eq!(&rebuilt, agents.memories());
    let heard = agents.memories().of(EntityId(5)).count();
    assert!(heard > 50, "Ada should remember plenty, remembers {heard}");
}

#[test]
fn a_world_restarted_every_37_ticks_matches_one_that_never_stopped() {
    let (calm, _) = run(1500, None);
    let (restarted, _) = run(1500, Some(37));
    let (calm, restarted) = (non_clock_events(&calm), non_clock_events(&restarted));
    let said = calm.iter().filter(|(_, p)| p.contains("sage.said")).count();
    assert!(said > 300, "agents should talk a lot, said {said}");
    assert_eq!(calm.len(), restarted.len());
    assert!(calm == restarted, "restarts changed what agents did");
}
