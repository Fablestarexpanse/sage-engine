//! Importance and retrieval in a real world: what an agent is shown when it thinks.

use std::collections::BTreeMap;

use sage_agents::llm::{Allowed, PromptParts};
use sage_agents::retrieval::importance;
use sage_agents::{Memory, Mind};
use sage_core::{
    Actor, ApplyError, Component, ComponentSet, Describable, EntityCreated, EntityId, Event,
    Journal, JournalError, Lexicon, Located, Occurred, Place, Upcasters,
};
use sage_store::SqliteLog;
use serde_json::json;

const HALL: EntityId = EntityId(1);
const BO: EntityId = EntityId(2);
const WREN: EntityId = EntityId(3);

fn set<C: Component>(id: EntityId, c: &C) -> Event {
    Event::ComponentSet(ComponentSet {
        id,
        component: C::NAME.into(),
        component_version: C::VERSION,
        data: serde_json::to_value(c).unwrap(),
    })
}

fn mind() -> Mind {
    Mind {
        driver: "llm".into(),
        think_every: 1,
        persona: String::new(),
        goals: vec![],
        rules: vec![],
        importance: BTreeMap::new(),
        reflect_threshold: None,
    }
}

/// A Hall with Bo and Wren, the agent.
fn journal() -> Journal<SqliteLog> {
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
    journal
        .commit(
            0,
            &[
                Event::EntityCreated(EntityCreated { id: HALL }),
                Event::EntityCreated(EntityCreated { id: BO }),
                Event::EntityCreated(EntityCreated { id: WREN }),
                set(HALL, &Place {}),
                set(HALL, &named("Hall")),
                set(BO, &named("Bo")),
                set(BO, &Actor {}),
                set(BO, &Located { within: HALL }),
                set(WREN, &named("Wren")),
                set(WREN, &Actor {}),
                set(WREN, &Located { within: HALL }),
                set(WREN, &mind()),
            ],
        )
        .unwrap();
    journal
}

fn occurred(
    kind: &str,
    actor: EntityId,
    targets: Vec<EntityId>,
    data: serde_json::Value,
) -> Occurred {
    Occurred {
        kind: kind.into(),
        kind_version: 1,
        actor: Some(actor),
        places: vec![HALL],
        targets,
        data,
        audience: vec![BO, WREN],
    }
}

#[test]
fn importance_follows_the_rules_and_mind_weights_override_them() {
    let journal = journal();
    let world = journal.world();
    let m = mind();
    let score = |o: &Occurred| importance(world, WREN, &m, o);

    assert_eq!(
        score(&occurred(
            "sage.command",
            WREN,
            vec![],
            json!({"text": "look"})
        )),
        1.0
    );
    assert_eq!(
        score(&occurred("sage.said", WREN, vec![], json!({"text": "hi"}))),
        2.0
    );
    assert_eq!(
        score(&occurred(
            "sage.mind.reflected",
            WREN,
            vec![],
            json!({"text": "Bo lies."})
        )),
        7.0
    );
    assert_eq!(
        score(&occurred(
            "sage.dialogue.told",
            BO,
            vec![WREN],
            json!({"text": "psst"})
        )),
        8.0
    );
    assert_eq!(
        score(&occurred(
            "sage.said",
            BO,
            vec![],
            json!({"text": "Wren, over here!"})
        )),
        6.0
    );
    assert_eq!(
        score(&occurred(
            "sage.said",
            BO,
            vec![],
            json!({"text": "Wrench please"})
        )),
        4.0
    );
    assert_eq!(
        score(&occurred(
            "sage.travelled",
            BO,
            vec![],
            json!({"label": "out"})
        )),
        2.0
    );
    assert_eq!(score(&occurred("sage.emoted", BO, vec![], json!({}))), 3.0);

    let mut weighted = mind();
    weighted.importance.insert("sage.travelled".into(), 9.5);
    assert_eq!(
        importance(
            world,
            WREN,
            &weighted,
            &occurred("sage.travelled", BO, vec![], json!({}))
        ),
        9.5
    );
}

#[test]
fn the_prompt_keeps_what_matters_not_just_what_is_recent() {
    let journal = journal();
    let world = journal.world();
    let m = mind();

    let mut memories = vec![Memory {
        tick: 10,
        occurred: occurred(
            "sage.dialogue.told",
            BO,
            vec![WREN],
            json!({"text": "The key to the north gate is under the loose stone."}),
        ),
    }];
    for tick in 11..60 {
        memories.push(Memory {
            tick,
            occurred: occurred(
                "sage.said",
                BO,
                vec![],
                json!({ "text": format!("idle chatter number {tick}") }),
            ),
        });
    }
    let refs: Vec<&Memory> = memories.iter().collect();
    let mut lexicon = Lexicon::core_english();
    lexicon.set("sage.dialogue.told.target", "{actor} tells you, \"{text}\"");
    let allowed = Allowed {
        verbs: vec!["say".into()],
        exits: vec![],
    };

    let parts = PromptParts::gather(world, WREN, &m, &refs, &allowed, &lexicon, 60);
    assert_eq!(parts.candidates.len(), 50);
    let messages = parts.assemble(&parts.lexical_relevance());
    let user = &messages[1].content;
    let lines: Vec<&str> = user.lines().filter(|l| l.starts_with("[tick ")).collect();

    assert!(
        user.contains("loose stone"),
        "the important old tell survives: {user}"
    );
    for tick in 55..60 {
        assert!(user.contains(&format!("chatter number {tick}")), "{user}");
    }
    assert!(
        !user.contains("chatter number 11\""),
        "old chatter drops out: {user}"
    );
    assert!(
        lines.len() <= 18,
        "5 newest + 3 most important + 10 best at most: {lines:?}"
    );
    assert!(lines[0].starts_with("[tick 10]"), "oldest first: {lines:?}");
}

#[test]
fn the_world_refuses_bad_v2_mind_fields_and_accepts_v1_minds() {
    let mut journal = journal();
    let mut too_heavy = mind();
    too_heavy.importance.insert("sage.said".into(), 11.0);
    let mut bad_kind = mind();
    bad_kind.importance.insert("said".into(), 5.0);
    let never = Mind {
        reflect_threshold: Some(0.0),
        ..mind()
    };
    for bad in [too_heavy, bad_kind, never] {
        let err = journal.commit(1, &[set(WREN, &bad)]).unwrap_err();
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

    // Data written as sage.mind v1 before these fields existed still applies.
    journal
        .commit(
            1,
            &[Event::ComponentSet(ComponentSet {
                id: WREN,
                component: Mind::NAME.into(),
                component_version: 1,
                data: json!({"driver": "scripted", "think_every": 4, "rules": []}),
            })],
        )
        .unwrap();
    let upcast = journal.world().get::<Mind>(WREN).unwrap();
    assert_eq!(upcast.think_every, 4);
    assert!(upcast.importance.is_empty() && upcast.reflect_threshold.is_none());
}
