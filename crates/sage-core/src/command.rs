//! Commands: the one interface through which players and agents act.
//!
//! An actor submits text such as `go onward`. At the start of the next tick the scheduler
//! logs it as a `sage.command` occurrence, finds the handler for its verb, and commits the
//! command and the handler's events as one batch. Handlers propose events like systems do; the
//! world validates them. Nothing an agent does bypasses this path.

use std::collections::BTreeMap;
use std::sync::Arc;

use serde_json::json;

use crate::Component;
use crate::components::{Link, Located};
use crate::event::{ComponentSet, Event, Occurred};
use crate::lexicon::Line;
use crate::world::{ApplyError, EntityId, World};

/// What a handler wants done.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CommandOutcome {
    /// Events to commit with the command, all or nothing.
    pub events: Vec<Event>,
    /// Private lines for the acting actor only.
    pub output: Vec<Line>,
}

/// Handles one or more verbs.
pub trait CommandHandler {
    /// Stable name, used in reports.
    fn name(&self) -> &'static str;

    /// Verbs this handler owns, lowercase.
    fn verbs(&self) -> Vec<String>;

    /// Handles `verb args` from `actor`. An error suspends the handler.
    fn handle(
        &mut self,
        world: &Arc<World>,
        actor: EntityId,
        verb: &str,
        args: &str,
        tick: u64,
    ) -> Result<CommandOutcome, String>;
}

/// What became of one submitted command.
#[derive(Clone, Debug, PartialEq)]
pub enum CommandResult {
    /// Handled and committed.
    Handled {
        /// Handler name.
        handler: &'static str,
    },
    /// No handler owns the verb and no link has that label. The command is still logged.
    UnknownVerb,
    /// The submitter is not a live actor. Nothing is logged.
    NotAnActor,
    /// The command was empty. Nothing is logged.
    Empty,
    /// The world refused the handler's events. The command alone is logged.
    Refused {
        /// Handler name.
        handler: &'static str,
        /// Why.
        error: ApplyError,
    },
    /// The handler failed and is now suspended. The command alone is logged.
    HandlerFailed {
        /// Handler name.
        handler: &'static str,
        /// The handler's error.
        reason: String,
    },
}

/// One submitted command and its result.
#[derive(Clone, Debug, PartialEq)]
pub struct CommandReport {
    /// Who submitted it.
    pub actor: EntityId,
    /// The text as submitted.
    pub text: String,
    /// What happened.
    pub result: CommandResult,
}

/// Registered handlers and the queue of submitted commands.
#[derive(Default)]
pub struct Commands {
    handlers: Vec<(Box<dyn CommandHandler>, bool)>,
    verbs: BTreeMap<String, usize>,
    queue: Vec<(EntityId, String)>,
}

impl Commands {
    /// No handlers.
    pub fn new() -> Commands {
        Commands::default()
    }

    /// Handlers for the core verbs: `look`, `go`, `say`, `emote`.
    pub fn with_core() -> Commands {
        let mut commands = Commands::new();
        commands
            .register(CoreCommands)
            .expect("core verbs do not conflict");
        commands
    }

    /// Adds a handler. Refuses one that claims a verb another handler owns, or a verb that is
    /// not a single lowercase word.
    pub fn register(&mut self, handler: impl CommandHandler + 'static) -> Result<(), String> {
        let verbs = handler.verbs();
        for verb in &verbs {
            if verb.is_empty()
                || !verb
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
            {
                return Err(format!(
                    "handler `{}` claims `{verb}`, which is not a lowercase word",
                    handler.name()
                ));
            }
            if let Some(owner) = self.verbs.get(verb) {
                return Err(format!(
                    "handler `{}` claims `{verb}`, already owned by `{}`",
                    handler.name(),
                    self.handlers[*owner].0.name()
                ));
            }
        }
        let index = self.handlers.len();
        for verb in verbs {
            self.verbs.insert(verb, index);
        }
        self.handlers.push((Box::new(handler), false));
        Ok(())
    }

    /// Queues a command for the next tick.
    pub fn submit(&mut self, actor: EntityId, text: impl Into<String>) {
        self.queue.push((actor, text.into()));
    }

    pub(crate) fn take_queue(&mut self) -> Vec<(EntityId, String)> {
        std::mem::take(&mut self.queue)
    }

    /// Maps `text` to a handler index, verb and arguments. A text that matches a link
    /// label leaving the actor's place is `go <label>`.
    pub(crate) fn resolve(
        &self,
        world: &World,
        actor: EntityId,
        text: &str,
    ) -> Option<(usize, String, String)> {
        let (verb, args) = match text.split_once(char::is_whitespace) {
            Some((verb, args)) => (verb.to_lowercase(), args.trim().to_owned()),
            None => (text.to_lowercase(), String::new()),
        };
        if let Some(index) = self.verbs.get(&verb) {
            return Some((*index, verb, args));
        }
        let here = world.get::<Located>(actor)?.within;
        world.link_named(here, text)?;
        let index = *self.verbs.get("go")?;
        Some((index, "go".to_owned(), text.to_owned()))
    }

    pub(crate) fn handler(&mut self, index: usize) -> (&mut dyn CommandHandler, &mut bool) {
        let (handler, suspended) = &mut self.handlers[index];
        (handler.as_mut(), suspended)
    }
}

/// The core verbs.
pub struct CoreCommands;

/// A `sage.*` occurrence.
pub fn occurrence(
    kind: &str,
    actor: EntityId,
    places: Vec<EntityId>,
    targets: Vec<EntityId>,
    data: serde_json::Value,
) -> Event {
    Event::Occurred(Occurred {
        kind: kind.to_owned(),
        kind_version: 1,
        actor: Some(actor),
        places,
        targets,
        data,
    })
}

impl CommandHandler for CoreCommands {
    fn name(&self) -> &'static str {
        "sage.core"
    }

    fn verbs(&self) -> Vec<String> {
        ["look", "go", "say", "emote"].map(String::from).to_vec()
    }

    fn handle(
        &mut self,
        world: &Arc<World>,
        actor: EntityId,
        verb: &str,
        args: &str,
        _tick: u64,
    ) -> Result<CommandOutcome, String> {
        let here = world.get::<Located>(actor).map(|l| l.within);
        let mut outcome = CommandOutcome::default();
        match verb {
            "look" => match here {
                None => outcome.output.push(Line::new("sage.look.nowhere")),
                Some(place) => outcome.output = look(world, actor, place),
            },
            "go" => match (here, args) {
                (_, "") => outcome.output.push(Line::new("sage.go.where")),
                (None, _) => outcome.output.push(Line::new("sage.look.nowhere")),
                (Some(place), label) => match world.link_named(place, label) {
                    None => outcome
                        .output
                        .push(Line::new("sage.go.no-way").with("label", label)),
                    Some((link_id, Link { to, label, .. })) => {
                        outcome.events.push(Event::ComponentSet(ComponentSet {
                            id: actor,
                            component: Located::NAME.into(),
                            component_version: Located::VERSION,
                            data: json!({ "within": to }),
                        }));
                        outcome.events.push(occurrence(
                            "sage.travelled",
                            actor,
                            vec![place, to],
                            Vec::new(),
                            json!({ "label": label, "link": link_id, "from": place, "to": to }),
                        ));
                        outcome.output = look(world, actor, to);
                    }
                },
            },
            "say" | "emote" => {
                let (kind, empty) = if verb == "say" {
                    ("sage.said", "sage.say.what")
                } else {
                    ("sage.emoted", "sage.emote.what")
                };
                match (here, args) {
                    (_, "") => outcome.output.push(Line::new(empty)),
                    (None, _) => outcome.output.push(Line::new("sage.look.nowhere")),
                    (Some(place), text) => outcome.events.push(occurrence(
                        kind,
                        actor,
                        vec![place],
                        Vec::new(),
                        json!({ "text": text }),
                    )),
                }
            }
            other => return Err(format!("core commands do not handle `{other}`")),
        }
        Ok(outcome)
    }
}

/// Lines describing `place` to `actor`. Uses the world as it is before the command's own
/// events apply, so after `go` it shows the destination's other occupants.
fn look(world: &World, actor: EntityId, place: EntityId) -> Vec<Line> {
    let mut lines = Vec::new();
    let described = world.get::<crate::Describable>(place);
    let mut line = Line::new("sage.look.place");
    if let Some(d) = described {
        line = line
            .with("name", d.name.clone())
            .with("description", d.description.clone());
    }
    lines.push(line);
    let exits: Vec<String> = world
        .links_from(place)
        .into_iter()
        .map(|(_, link)| link.label)
        .collect();
    lines.push(if exits.is_empty() {
        Line::new("sage.look.no-exits")
    } else {
        Line::new("sage.look.exits").with("exits", exits.join(", "))
    });
    let things: Vec<String> = world
        .contents(place)
        .into_iter()
        .filter(|id| *id != actor)
        .filter_map(|id| world.name_of(id))
        .collect();
    if !things.is_empty() {
        lines.push(Line::new("sage.look.contents").with("things", things.join(", ")));
    }
    lines
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::journal::test_log::MemoryLog;
    use crate::{
        Actor, ComponentRegistry, Delivery, Describable, EntityCreated, Journal, Lexicon, Place,
        Scheduler, StepReport, Upcasters,
    };

    const HALL: EntityId = EntityId(1);
    const YARD: EntityId = EntityId(2);
    const ADA: EntityId = EntityId(5);
    const BO: EntityId = EntityId(6);
    const CY: EntityId = EntityId(7);
    const LAMP: EntityId = EntityId(8);

    fn set<C: Component>(id: u64, c: &C) -> Event {
        Event::ComponentSet(ComponentSet {
            id: EntityId(id),
            component: C::NAME.into(),
            component_version: C::VERSION,
            data: serde_json::to_value(c).unwrap(),
        })
    }

    fn named(name: &str) -> Describable {
        Describable {
            name: name.into(),
            description: format!("{name}, plainly."),
        }
    }

    /// Hall (1) and Yard (2); link 3 Hall->Yard "out", link 4 Yard->Hall "in"; actors Ada (5)
    /// and Bo (6) in the Hall, Cy (7) in the Yard; a lamp (8, not an actor) in the Hall.
    fn world() -> (Journal<MemoryLog>, Scheduler) {
        let mut journal = Journal::open(
            MemoryLog::default(),
            ComponentRegistry::with_core(),
            Upcasters::new(),
        )
        .unwrap();
        let mut events: Vec<Event> = (1..=8)
            .map(|id| Event::EntityCreated(EntityCreated { id: EntityId(id) }))
            .collect();
        let link = |from, to, label: &str| Link {
            from: EntityId(from),
            to: EntityId(to),
            label: label.into(),
        };
        let within = |id| Located {
            within: EntityId(id),
        };
        events.extend([
            set(1, &Place {}),
            set(1, &named("Hall")),
            set(2, &Place {}),
            set(2, &named("Yard")),
            set(3, &link(1, 2, "out")),
            set(4, &link(2, 1, "in")),
            set(5, &named("Ada")),
            set(5, &Actor {}),
            set(5, &within(1)),
            set(6, &named("Bo")),
            set(6, &Actor {}),
            set(6, &within(1)),
            set(7, &named("Cy")),
            set(7, &Actor {}),
            set(7, &within(2)),
            set(8, &named("lamp")),
            set(8, &within(1)),
        ]);
        journal.commit(0, &events).unwrap();
        let scheduler = Scheduler::new(&journal, 1000);
        (journal, scheduler)
    }

    /// Every delivery to `who`, rendered in core English; unrenderable lines are dropped.
    fn heard(report: &StepReport, who: EntityId) -> Vec<String> {
        let lexicon = Lexicon::core_english();
        report
            .deliveries
            .iter()
            .filter(|d: &&Delivery| d.to == who)
            .filter_map(|d| lexicon.render(&d.line))
            .collect()
    }

    fn step(
        journal: &mut Journal<MemoryLog>,
        scheduler: &mut Scheduler,
        commands: &[(EntityId, &str)],
    ) -> StepReport {
        for (actor, text) in commands {
            scheduler.submit(*actor, *text);
        }
        scheduler.step(journal).unwrap()
    }

    fn logged_commands(journal: &Journal<MemoryLog>) -> Vec<String> {
        journal
            .log()
            .events
            .iter()
            .filter(|e| e.record.event_type == "Occurred")
            .filter(|e| e.record.payload["kind"] == "sage.command")
            .map(|e| {
                e.record.payload["data"]["text"]
                    .as_str()
                    .unwrap()
                    .to_owned()
            })
            .collect()
    }

    #[test]
    fn look_describes_the_place_its_ways_and_whoever_else_is_there() {
        let (mut j, mut s) = world();
        let report = step(&mut j, &mut s, &[(ADA, "look")]);
        assert_eq!(
            heard(&report, ADA),
            ["Hall\nHall, plainly.", "Ways on: out.", "Here: Bo, lamp."]
        );
        assert!(heard(&report, BO).is_empty());
        assert_eq!(
            report.commands[0].result,
            CommandResult::Handled {
                handler: "sage.core"
            }
        );
    }

    #[test]
    fn going_moves_the_actor_and_both_places_perceive_it() {
        let (mut j, mut s) = world();
        let report = step(&mut j, &mut s, &[(ADA, "go out")]);
        assert_eq!(j.world().get::<Located>(ADA).unwrap().within, YARD);
        assert_eq!(
            heard(&report, ADA),
            [
                "You go out.",
                "Yard\nYard, plainly.",
                "Ways on: in.",
                "Here: Cy."
            ]
        );
        assert_eq!(heard(&report, BO), ["Ada leaves out."]);
        assert_eq!(heard(&report, CY), ["Ada arrives."]);
        assert!(report.deliveries.iter().all(|d| d.to != LAMP));
    }

    #[test]
    fn a_link_label_on_its_own_means_go() {
        let (mut j, mut s) = world();
        let report = step(&mut j, &mut s, &[(ADA, "out")]);
        assert_eq!(j.world().get::<Located>(ADA).unwrap().within, YARD);
        assert_eq!(heard(&report, CY), ["Ada arrives."]);
    }

    #[test]
    fn speech_reaches_actors_in_the_same_place_only() {
        let (mut j, mut s) = world();
        let report = step(
            &mut j,
            &mut s,
            &[(BO, "say  hello there "), (ADA, "emote waves.")],
        );
        assert_eq!(
            heard(&report, ADA),
            ["Bo says, \"hello there\"", "Ada waves."]
        );
        assert_eq!(
            heard(&report, BO),
            ["You say, \"hello there\"", "Ada waves."]
        );
        assert!(heard(&report, CY).is_empty());
    }

    #[test]
    fn nonsense_is_logged_and_answered_but_changes_nothing() {
        let (mut j, mut s) = world();
        let before = j.world().snapshot().entities;
        let report = step(
            &mut j,
            &mut s,
            &[(ADA, "dance wildly"), (ADA, "go sideways"), (ADA, "say")],
        );
        assert_eq!(
            heard(&report, ADA),
            [
                "Nothing here understands \"dance\".",
                "There is no way sideways from here.",
                "Say what?"
            ]
        );
        assert_eq!(report.commands[0].result, CommandResult::UnknownVerb);
        assert_eq!(j.world().snapshot().entities, before);
        assert_eq!(logged_commands(&j), ["dance wildly", "go sideways", "say"]);
    }

    #[test]
    fn only_live_actors_can_command_and_empty_text_is_ignored() {
        let (mut j, mut s) = world();
        let report = step(
            &mut j,
            &mut s,
            &[(LAMP, "look"), (EntityId(99), "look"), (ADA, "   ")],
        );
        let results: Vec<_> = report.commands.iter().map(|c| c.result.clone()).collect();
        assert_eq!(
            results,
            [
                CommandResult::NotAnActor,
                CommandResult::NotAnActor,
                CommandResult::Empty
            ]
        );
        assert!(logged_commands(&j).is_empty());
        assert!(report.deliveries.is_empty());
    }

    struct Breaker {
        fail: bool,
    }

    impl CommandHandler for Breaker {
        fn name(&self) -> &'static str {
            "test.breaker"
        }

        fn verbs(&self) -> Vec<String> {
            vec!["break".into()]
        }

        fn handle(
            &mut self,
            _: &Arc<World>,
            _: EntityId,
            _: &str,
            _: &str,
            _: u64,
        ) -> Result<CommandOutcome, String> {
            if self.fail {
                return Err("broke itself".into());
            }
            Ok(CommandOutcome {
                events: vec![set(99, &Place {})],
                output: vec![Line::new("test.never-shown")],
            })
        }
    }

    #[test]
    fn refused_handler_events_leave_only_the_logged_command() {
        let (mut j, mut s) = world();
        s.commands_mut().register(Breaker { fail: false }).unwrap();
        let report = step(&mut j, &mut s, &[(ADA, "break")]);
        assert!(matches!(
            report.commands[0].result,
            CommandResult::Refused {
                handler: "test.breaker",
                error: ApplyError::NoSuchEntity(EntityId(99))
            }
        ));
        assert_eq!(heard(&report, ADA), ["That did not work."]);
        assert_eq!(logged_commands(&j), ["break"]);
    }

    #[test]
    fn failing_handler_is_suspended() {
        let (mut j, mut s) = world();
        s.commands_mut().register(Breaker { fail: true }).unwrap();
        let first = step(&mut j, &mut s, &[(ADA, "break")]);
        let second = step(&mut j, &mut s, &[(ADA, "break"), (ADA, "look")]);
        assert!(matches!(
            &first.commands[0].result,
            CommandResult::HandlerFailed { reason, .. } if reason == "broke itself"
        ));
        assert!(matches!(
            &second.commands[0].result,
            CommandResult::HandlerFailed { reason, .. } if reason == "handler is suspended"
        ));
        assert!(matches!(
            second.commands[1].result,
            CommandResult::Handled { .. }
        ));
    }

    struct Claims(&'static str);

    impl CommandHandler for Claims {
        fn name(&self) -> &'static str {
            "test.claims"
        }

        fn verbs(&self) -> Vec<String> {
            vec![self.0.into()]
        }

        fn handle(
            &mut self,
            _: &Arc<World>,
            _: EntityId,
            _: &str,
            _: &str,
            _: u64,
        ) -> Result<CommandOutcome, String> {
            Ok(CommandOutcome::default())
        }
    }

    #[test]
    fn verbs_cannot_be_claimed_twice_or_malformed() {
        let mut commands = Commands::with_core();
        let err = commands.register(Claims("say")).unwrap_err();
        assert!(err.contains("already owned by `sage.core`"), "{err}");
        assert!(commands.register(Claims("Shout")).is_err());
        assert!(commands.register(Claims("shout loudly")).is_err());
        assert!(commands.register(Claims("shout")).is_ok());
    }

    #[test]
    fn a_log_of_commands_replays_to_the_same_world() {
        let (mut j, mut s) = world();
        step(&mut j, &mut s, &[(ADA, "out"), (BO, "say bye")]);
        step(&mut j, &mut s, &[(ADA, "emote waves"), (ADA, "in")]);
        let live = j.world().snapshot().to_bytes();
        let replayed = Journal::open_from_genesis(
            j.into_log(),
            ComponentRegistry::with_core(),
            Upcasters::new(),
        )
        .unwrap();
        assert_eq!(replayed.world().snapshot().to_bytes(), live);
        assert_eq!(replayed.world().get::<Located>(ADA).unwrap().within, HALL);
    }

    #[test]
    fn world_refuses_malformed_occurrences() {
        let (mut j, _) = world();
        let bad = |kind: &str, places: Vec<EntityId>| {
            Event::Occurred(Occurred {
                kind: kind.into(),
                kind_version: 1,
                actor: Some(ADA),
                places,
                targets: vec![],
                data: json!({}),
            })
        };
        for event in [
            bad("said", vec![HALL]),
            bad("Sage.Said", vec![HALL]),
            bad("sage.said", vec![EntityId(99)]),
        ] {
            let err = j.commit(1, &[event]).unwrap_err();
            assert!(
                matches!(
                    err,
                    crate::JournalError::Refused {
                        error: ApplyError::BadOccurrence { .. },
                        ..
                    }
                ),
                "{err}"
            );
        }
    }
}
