//! Scripted agents in a real world: they perceive, decide by rules, and act only through
//! submitted commands.

use sage_agents::{Agents, Mind, Rule, When};
use sage_core::{
    Actor, ApplyError, Component, ComponentSet, Describable, EntityCreated, EntityId, Event,
    EventLog, Journal, JournalError, Lexicon, Link, Located, Place, Scheduler, StepReport,
    Upcasters,
};
use sage_store::SqliteLog;

const HALL: EntityId = EntityId(1);
const YARD: EntityId = EntityId(2);
const BO: EntityId = EntityId(5);
const AGENT: EntityId = EntityId(6);

fn set<C: Component>(id: EntityId, c: &C) -> Event {
    Event::ComponentSet(ComponentSet {
        id,
        component: C::NAME.into(),
        component_version: C::VERSION,
        data: serde_json::to_value(c).unwrap(),
    })
}

fn rule(when: When, command: &str) -> Rule {
    Rule {
        when,
        command: command.into(),
    }
}

fn mind(think_every: u64, rules: Vec<Rule>) -> Mind {
    Mind {
        driver: "scripted".into(),
        think_every,
        persona: "A test agent.".into(),
        goals: vec![],
        rules,
        importance: Default::default(),
        reflect_threshold: None,
    }
}

/// Hall (1) and Yard (2) joined both ways; Bo (5), a player, and the agent Greta (6) in the
/// Hall.
fn world(agent_mind: Mind) -> (Journal<SqliteLog>, Scheduler) {
    let mut journal = Journal::open(
        SqliteLog::open_in_memory().unwrap(),
        sage_agents::registry(),
        Upcasters::core(),
    )
    .unwrap();
    let named = |name: &str| Describable {
        name: name.into(),
        description: String::new(),
    };
    let mut events: Vec<Event> = (1..=6)
        .map(|id| Event::EntityCreated(EntityCreated { id: EntityId(id) }))
        .collect();
    events.extend([
        set(HALL, &Place {}),
        set(HALL, &named("Hall")),
        set(YARD, &Place {}),
        set(YARD, &named("Yard")),
        set(
            EntityId(3),
            &Link {
                from: HALL,
                to: YARD,
                label: "out".into(),
            },
        ),
        set(
            EntityId(4),
            &Link {
                from: YARD,
                to: HALL,
                label: "in".into(),
            },
        ),
        set(BO, &named("Bo")),
        set(BO, &Actor {}),
        set(BO, &Located { within: HALL }),
        set(AGENT, &named("Greta")),
        set(AGENT, &Actor {}),
        set(AGENT, &Located { within: HALL }),
        set(AGENT, &agent_mind),
    ]);
    journal.commit(0, &events).unwrap();
    let scheduler = Scheduler::new(&journal, 1000);
    (journal, scheduler)
}

/// Steps `ticks` times, feeding agents' perceptions back and submitting their commands, with
/// `player` commands queued at the given ticks.
fn run(
    journal: &mut Journal<SqliteLog>,
    scheduler: &mut Scheduler,
    ticks: u64,
    player: &[(u64, &str)],
) -> Vec<StepReport> {
    let mut agents = Agents::new();
    let mut reports = Vec::new();
    for _ in 0..ticks {
        let next = scheduler.tick() + 1;
        for (tick, text) in player {
            if *tick == next {
                scheduler.submit(BO, *text);
            }
        }
        let report = scheduler.step(journal).unwrap();
        agents.observe(&report);
        for thought in agents.think(journal.world(), scheduler.tick() + 1) {
            scheduler.submit(thought.agent, thought.command);
        }
        reports.push(report);
    }
    reports
}

fn heard_by(reports: &[StepReport], who: EntityId) -> Vec<String> {
    let lexicon = Lexicon::core_english();
    reports
        .iter()
        .flat_map(|r| &r.deliveries)
        .filter(|d| d.to == who)
        .filter_map(|d| lexicon.render(&d.line))
        .collect()
}

fn agent_commands(reports: &[StepReport]) -> Vec<String> {
    reports
        .iter()
        .flat_map(|r| &r.commands)
        .filter(|c| c.actor == AGENT)
        .map(|c| c.text.clone())
        .collect()
}

#[test]
fn agent_answers_what_it_hears_through_the_player_command_path() {
    let greeter = mind(
        1,
        vec![rule(
            When {
                heard: Some("sage.said".into()),
                text_contains: Some("good day".into()),
                ..When::default()
            },
            "say Well met, {speaker}.",
        )],
    );
    let (mut j, mut s) = world(greeter);
    let reports = run(
        &mut j,
        &mut s,
        6,
        &[(2, "say Good day, Greta"), (4, "say nothing much")],
    );
    assert_eq!(agent_commands(&reports), ["say Well met, Bo."]);
    assert_eq!(
        heard_by(&reports, BO),
        [
            "You say, \"Good day, Greta\"",
            "Greta says, \"Well met, Bo.\"",
            "You say, \"nothing much\""
        ]
    );
    // The agent's action is in the log exactly as a player's would be.
    let logged: Vec<(u64, String)> = j
        .log()
        .connection()
        .prepare("SELECT tick, payload FROM events WHERE event_type = 'Occurred'")
        .unwrap()
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)? as u64, row.get::<_, String>(1)?))
        })
        .unwrap()
        .map(Result::unwrap)
        .filter(|(_, p)| p.contains("\"sage.command\"") && p.contains("\"actor\":6"))
        .collect();
    assert_eq!(logged.len(), 1);
    assert_eq!(
        logged[0].0, 3,
        "heard at tick 2, thought after it, acted at tick 3"
    );
}

#[test]
fn agent_does_not_answer_itself() {
    let echo = mind(
        1,
        vec![rule(
            When {
                heard: Some("sage.said".into()),
                ..When::default()
            },
            "say I heard: {text}",
        )],
    );
    let (mut j, mut s) = world(echo);
    let reports = run(&mut j, &mut s, 20, &[(1, "say hi")]);
    assert_eq!(agent_commands(&reports), ["say I heard: hi"]);
}

#[test]
fn wandering_agent_moves_and_the_run_is_repeatable() {
    let wanderer = || {
        mind(
            5,
            vec![rule(
                When {
                    chance: Some(0.6),
                    ..When::default()
                },
                "go {any_exit}",
            )],
        )
    };
    let (mut j1, mut s1) = world(wanderer());
    let reports = run(&mut j1, &mut s1, 200, &[]);
    let moves = agent_commands(&reports);
    assert!(
        (15..=30).contains(&moves.len()),
        "40 thinks at 60% chance, got {}",
        moves.len()
    );
    assert!(
        moves.iter().all(|m| m == "go out" || m == "go in"),
        "{moves:?}"
    );

    let (mut j2, mut s2) = world(wanderer());
    run(&mut j2, &mut s2, 200, &[]);
    assert_eq!(
        j1.world().snapshot().to_bytes(),
        j2.world().snapshot().to_bytes()
    );
    assert_eq!(
        j1.log().read_page(1, 100_000).unwrap(),
        j2.log().read_page(1, 100_000).unwrap(),
        "same world, same rules, same log"
    );
}

#[test]
fn alone_and_every_conditions() {
    let loner = mind(
        1,
        vec![rule(
            When {
                alone: Some(true),
                every: Some(3),
                ..When::default()
            },
            "emote stretches.",
        )],
    );
    let (mut j, mut s) = world(loner);
    // Bo is in the Hall for ticks 1-5, leaves at tick 6.
    let reports = run(&mut j, &mut s, 12, &[(6, "go out")]);
    let commands: Vec<u64> = reports
        .iter()
        .flat_map(|r| r.commands.iter().map(move |c| (r.tick, c)))
        .filter(|(_, c)| c.actor == AGENT)
        .map(|(tick, _)| tick)
        .collect();
    assert_eq!(
        commands,
        [9, 12],
        "alone from tick 6; acts on multiples of 3"
    );
}

#[test]
fn a_mind_without_an_actor_does_nothing() {
    let (mut j, _) = world(mind(1, vec![rule(When::default(), "emote exists.")]));
    j.commit(
        1,
        &[Event::ComponentRemoved(sage_core::ComponentRemoved {
            id: AGENT,
            component: Actor::NAME.into(),
        })],
    )
    .unwrap();
    // A fresh scheduler, so the removal commit and the run share one clock.
    let mut s2 = Scheduler::new(&j, 1000);
    let reports = run(&mut j, &mut s2, 5, &[]);
    assert!(agent_commands(&reports).is_empty());
}

#[test]
fn the_world_refuses_nonsense_minds() {
    let (mut j, _) = world(mind(1, vec![]));
    let bad_minds = [
        mind(0, vec![]),
        Mind {
            driver: "telepathy".into(),
            ..mind(1, vec![])
        },
        mind(
            1,
            vec![rule(
                When {
                    chance: Some(1.5),
                    ..When::default()
                },
                "look",
            )],
        ),
        mind(
            1,
            vec![rule(
                When {
                    every: Some(0),
                    ..When::default()
                },
                "look",
            )],
        ),
        mind(
            1,
            vec![rule(
                When {
                    text_contains: Some("hi".into()),
                    ..When::default()
                },
                "look",
            )],
        ),
        mind(1, vec![rule(When::default(), "say {speaker}")]),
        mind(1, vec![rule(When::default(), "go {somewhere}")]),
        mind(1, vec![rule(When::default(), "say {unclosed")]),
        mind(1, vec![rule(When::default(), "   ")]),
        mind(1, vec![rule(When::default(), "@think")]),
        Mind {
            driver: "hybrid".into(),
            ..mind(1, vec![rule(When::default(), "@thinkhard")])
        },
    ];
    for bad in bad_minds {
        let err = j.commit(1, &[set(AGENT, &bad)]).unwrap_err();
        assert!(
            matches!(
                err,
                JournalError::Refused {
                    error: ApplyError::ComponentData { .. },
                    ..
                }
            ),
            "{bad:?} -> {err}"
        );
    }
    let unknown_field = serde_json::json!({"driver": "scripted", "think_every": 1, "mood": "sly"});
    let err = j
        .commit(
            1,
            &[Event::ComponentSet(ComponentSet {
                id: AGENT,
                component: Mind::NAME.into(),
                component_version: 1,
                data: unknown_field,
            })],
        )
        .unwrap_err();
    assert!(err.to_string().contains("mood"), "{err}");
}
