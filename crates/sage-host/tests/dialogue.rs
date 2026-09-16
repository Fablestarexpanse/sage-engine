//! Plugin command handlers, through the real first-party `sage.dialogue` plugin: commands from
//! actors reach a sandboxed handler, its occurrences are perceived by the right actors only, and
//! a plugin cannot emit occurrences under another name.

use std::sync::Arc;

use sage_core::{
    Actor, CommandResult, Component, ComponentRegistry, ComponentSet, Describable, EntityCreated,
    EntityId, Event, Journal, Lexicon, Link, Located, Place, Scheduler, StepReport, System,
    Upcasters, World,
};
use sage_host::{GRANTABLE, Limits, PluginHost, PluginSystem};
use sage_store::SqliteLog;

const ADA: EntityId = EntityId(5);
const BO: EntityId = EntityId(6);
const CY: EntityId = EntityId(7);
const DEE: EntityId = EntityId(8);

fn set<C: Component>(id: u64, c: &C) -> Event {
    Event::ComponentSet(ComponentSet {
        id: EntityId(id),
        component: C::NAME.into(),
        component_version: C::VERSION,
        data: serde_json::to_value(c).unwrap(),
    })
}

/// Hall (1), Yard (2), links 3 and 4; actors Ada (5), Bo (6) and Dee (8) in the Hall, Cy (7)
/// in the Yard.
fn journal() -> Journal<SqliteLog> {
    let mut journal = Journal::open(
        SqliteLog::open_in_memory().unwrap(),
        ComponentRegistry::with_core(),
        Upcasters::core(),
    )
    .unwrap();
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
    for (id, name, place) in [(5, "Ada", 1), (6, "Bo", 1), (7, "Cy", 2), (8, "Dee", 1)] {
        events.extend([
            set(id, &named(name)),
            set(id, &Actor {}),
            set(
                id,
                &Located {
                    within: EntityId(place),
                },
            ),
        ]);
    }
    journal.commit(0, &events).unwrap();
    journal
}

fn dialogue(host: &PluginHost) -> PluginSystem {
    let dir = sage_build::first_party_plugin("sage.dialogue");
    let wasm = std::fs::read(dir.join("plugin.wasm")).unwrap();
    host.load(&wasm, &GRANTABLE, Limits::default()).unwrap()
}

fn heard(lexicon: &Lexicon, report: &StepReport, who: EntityId) -> Vec<String> {
    report
        .deliveries
        .iter()
        .filter(|d| d.to == who)
        .filter_map(|d| lexicon.render(&d.line))
        .collect()
}

#[test]
fn tell_reaches_only_the_teller_and_the_named_actor() {
    let host = PluginHost::new().unwrap();
    let mut journal = journal();
    let plugin = dialogue(&host);
    assert_eq!(plugin.verbs(), ["tell"]);

    let mut lexicon = Lexicon::core_english();
    for (key, template) in plugin.lexicon() {
        assert!(key.starts_with("sage.dialogue."), "{key}");
        lexicon.set(key, template);
    }

    let mut scheduler = Scheduler::new(&journal, 1000);
    scheduler
        .commands_mut()
        .register(plugin.command_handler().unwrap())
        .unwrap();
    scheduler.add(plugin);

    scheduler.submit(ADA, "tell bo meet me outside");
    scheduler.submit(ADA, "tell cy hello");
    scheduler.submit(ADA, "tell");
    let report = scheduler.step(&mut journal).unwrap();

    assert_eq!(
        report.commands[0].result,
        CommandResult::Handled {
            handler: "sage.dialogue"
        }
    );
    assert_eq!(
        heard(&lexicon, &report, ADA),
        [
            "You tell Bo, \"meet me outside\"",
            "Nobody here answers to \"cy\".",
            "Tell whom what?"
        ]
    );
    assert_eq!(
        heard(&lexicon, &report, BO),
        ["Ada tells you, \"meet me outside\""]
    );
    assert!(
        heard(&lexicon, &report, DEE).is_empty(),
        "Dee is in the room but not told"
    );
    assert!(heard(&lexicon, &report, CY).is_empty());
    assert!(report.suspended.is_empty(), "{report:?}");

    let live = journal.world().snapshot().to_bytes();
    let replayed = Journal::open_from_genesis(
        journal.into_log(),
        ComponentRegistry::with_core(),
        Upcasters::core(),
    )
    .unwrap();
    assert_eq!(replayed.world().snapshot().to_bytes(), live);
}

#[test]
fn a_verb_cannot_be_claimed_by_two_plugins() {
    let host = PluginHost::new().unwrap();
    let mut commands = sage_core::Commands::with_core();
    assert!(
        commands
            .register(dialogue(&host).command_handler().unwrap())
            .is_ok()
    );
    let err = commands
        .register(dialogue(&host).command_handler().unwrap())
        .unwrap_err();
    assert!(err.contains("already owned by `sage.dialogue`"), "{err}");
}

#[test]
fn system_only_plugins_have_no_command_handler() {
    let host = PluginHost::new().unwrap();
    let mover = host
        .load(
            &sage_build::test_plugin("mover"),
            &GRANTABLE,
            Limits::default(),
        )
        .unwrap();
    assert!(mover.command_handler().is_none());
    assert!(mover.verbs().is_empty() && mover.lexicon().is_empty());
}

#[test]
fn a_plugin_cannot_emit_another_names_occurrences() {
    let host = PluginHost::new().unwrap();
    let mut impostor = host
        .load(&sage_build::test_plugin("impostor"), &[], Limits::default())
        .unwrap();
    let journal = journal();
    let world: &Arc<World> = journal.world_handle();
    let err = impostor.run(world, 1).unwrap_err();
    assert!(
        err.contains("`sage.said` occurrence; plugin `fixture.impostor` may only emit kinds starting with `fixture.impostor.`"),
        "{err}"
    );
}
