//! The engine side of play. Runs on the engine thread between steps: signs players in, creates
//! their characters as ordinary events, submits their commands through the same path agents
//! use, and routes each delivery to the player whose character perceived it.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::mpsc::Receiver;

use sage_core::{
    Actor, Component, ComponentSet, Describable, EntityCreated, EntityId, Event, Journal, Lexicon,
    Located, Place, Scheduler, StepReport, World,
};
use sage_store::SqliteLog;
use tokio::sync::mpsc::UnboundedSender;

use crate::accounts::Accounts;
use crate::net::Inbound;
use crate::protocol::{COMMANDS_PER_TICK, MAX_COMMAND_CHARS, PlaceView, ServerFrame};

struct Session {
    out: UnboundedSender<ServerFrame>,
    account: Option<String>,
    character: Option<EntityId>,
    commands_this_tick: u32,
}

impl Session {
    fn send(&self, frame: ServerFrame) {
        let _ = self.out.send(frame);
    }
}

/// Everyone connected.
pub struct Players {
    inbound: Receiver<Inbound>,
    accounts: Accounts,
    sessions: BTreeMap<u64, Session>,
    start_place: Option<EntityId>,
    lexicon: Lexicon,
}

impl Players {
    /// Players whose requests arrive on `inbound`, stored in `accounts`.
    pub fn new(
        inbound: Receiver<Inbound>,
        accounts: Accounts,
        start_place: Option<EntityId>,
        lexicon: Lexicon,
    ) -> Players {
        Players {
            inbound,
            accounts,
            sessions: BTreeMap::new(),
            start_place,
            lexicon,
        }
    }

    /// Connected sessions with a character.
    pub fn signed_in(&self) -> usize {
        self.sessions
            .values()
            .filter(|s| s.character.is_some())
            .count()
    }

    /// Handles everything that arrived since the last tick. Commands are queued for the next
    /// step; new characters are committed now.
    pub fn before_step(
        &mut self,
        journal: &mut Journal<SqliteLog>,
        scheduler: &mut Scheduler,
    ) -> Result<(), String> {
        for session in self.sessions.values_mut() {
            session.commands_this_tick = 0;
        }
        while let Ok(message) = self.inbound.try_recv() {
            match message {
                Inbound::Connected { session, out } => {
                    self.sessions.insert(
                        session,
                        Session {
                            out,
                            account: None,
                            character: None,
                            commands_this_tick: 0,
                        },
                    );
                }
                Inbound::Disconnected { session } => {
                    self.sessions.remove(&session);
                }
                Inbound::Command { session, text } => {
                    self.command(session, text, journal, scheduler)
                }
                Inbound::Register {
                    session,
                    name,
                    password_hash,
                } => self.register(session, name, password_hash, journal, scheduler)?,
                Inbound::LoggedIn { session, name } => {
                    self.log_in(session, name, journal, scheduler)?
                }
            }
        }
        Ok(())
    }

    fn command(
        &mut self,
        session: u64,
        text: String,
        journal: &Journal<SqliteLog>,
        scheduler: &mut Scheduler,
    ) {
        let Some(s) = self.sessions.get_mut(&session) else {
            return;
        };
        let Some(character) = s.character else {
            s.send(ServerFrame::error(
                "not-signed-in",
                "Register or log in first.",
            ));
            return;
        };
        if text.chars().count() > MAX_COMMAND_CHARS {
            s.send(ServerFrame::error(
                "too-long",
                format!("Commands are at most {MAX_COMMAND_CHARS} characters."),
            ));
            return;
        }
        if s.commands_this_tick >= COMMANDS_PER_TICK {
            s.send(ServerFrame::error(
                "slow-down",
                "Too many commands at once.",
            ));
            return;
        }
        if !journal.world().contains(character) {
            s.send(ServerFrame::error(
                "no-character",
                "Your character is gone. Log in again.",
            ));
            return;
        }
        s.commands_this_tick += 1;
        scheduler.submit(character, text);
    }

    fn register(
        &mut self,
        session: u64,
        name: String,
        password_hash: String,
        journal: &mut Journal<SqliteLog>,
        scheduler: &mut Scheduler,
    ) -> Result<(), String> {
        if !self.sessions.contains_key(&session) {
            return Ok(());
        }
        let taken = self.accounts.find(&name)?.is_some() || name_in_use(journal.world(), &name);
        if taken {
            self.sessions[&session].send(ServerFrame::error(
                "name-taken",
                format!("The name {name} is taken."),
            ));
            return Ok(());
        }
        let character = match self.create_character(&name, journal, scheduler) {
            Ok(character) => character,
            Err(message) => {
                self.sessions[&session].send(ServerFrame::error("no-start-place", message));
                return Ok(());
            }
        };
        self.accounts.create(&name, &password_hash, character.0)?;
        self.attach(session, name, character, journal, scheduler);
        Ok(())
    }

    fn log_in(
        &mut self,
        session: u64,
        name: String,
        journal: &mut Journal<SqliteLog>,
        scheduler: &mut Scheduler,
    ) -> Result<(), String> {
        if !self.sessions.contains_key(&session) {
            return Ok(());
        }
        let Some(account) = self.accounts.find(&name)? else {
            self.sessions[&session].send(ServerFrame::error("bad-login", "No such account."));
            return Ok(());
        };
        let world = journal.world();
        let character = match account.character.map(EntityId) {
            Some(id) if world.contains(id) && world.get::<Actor>(id).is_some() => id,
            _ => {
                let character = match self.create_character(&account.name, journal, scheduler) {
                    Ok(character) => character,
                    Err(message) => {
                        self.sessions[&session].send(ServerFrame::error("no-start-place", message));
                        return Ok(());
                    }
                };
                self.accounts.set_character(&account.name, character.0)?;
                character
            }
        };
        let replaced: Vec<u64> = self
            .sessions
            .iter()
            .filter(|(id, s)| {
                **id != session && s.account.as_deref() == Some(account.name.as_str())
            })
            .map(|(id, _)| *id)
            .collect();
        for old in replaced {
            if let Some(s) = self.sessions.remove(&old) {
                s.send(ServerFrame::Kicked {
                    reason: "Signed in from somewhere else.".into(),
                });
            }
        }
        self.attach(session, account.name, character, journal, scheduler);
        Ok(())
    }

    fn attach(
        &mut self,
        session: u64,
        name: String,
        character: EntityId,
        journal: &Journal<SqliteLog>,
        scheduler: &mut Scheduler,
    ) {
        let s = self.sessions.get_mut(&session).expect("checked by callers");
        s.account = Some(name.clone());
        s.character = Some(character);
        s.send(ServerFrame::Session {
            name,
            character: character.0,
        });
        s.send(state(journal.world(), character));
        scheduler.submit(character, "look");
    }

    /// Commits a new character named `name` at the start place, outside a step: its own
    /// transaction, at the current tick.
    fn create_character(
        &self,
        name: &str,
        journal: &mut Journal<SqliteLog>,
        scheduler: &Scheduler,
    ) -> Result<EntityId, String> {
        let world = journal.world();
        let place = self
            .start_place
            .filter(|p| world.get::<Place>(*p).is_some())
            .or_else(|| world.entities_with(Place::NAME).into_iter().next())
            .ok_or("This world has no place to start in yet.")?;
        let id = world.next_entity_id();
        let set = |component: &str, version: u32, data: serde_json::Value| {
            Event::ComponentSet(ComponentSet {
                id,
                component: component.into(),
                component_version: version,
                data,
            })
        };
        let events = [
            Event::EntityCreated(EntityCreated { id }),
            set(
                Describable::NAME,
                Describable::VERSION,
                serde_json::json!({"name": name, "description": ""}),
            ),
            set(Actor::NAME, Actor::VERSION, serde_json::json!({})),
            set(
                Located::NAME,
                Located::VERSION,
                serde_json::json!({"within": place}),
            ),
        ];
        journal
            .commit(scheduler.tick().max(journal.world().tick()), &events)
            .map_err(|e| e.to_string())?;
        Ok(id)
    }

    /// Sends each signed-in player what their character perceived this step, then a `state`
    /// frame if anything reached them.
    pub fn after_step(&mut self, world: &World, report: &StepReport) {
        let by_character: BTreeMap<EntityId, u64> = self
            .sessions
            .iter()
            .filter_map(|(id, s)| s.character.map(|c| (c, *id)))
            .collect();
        let mut reached = BTreeSet::new();
        for delivery in &report.deliveries {
            let Some(session) = by_character.get(&delivery.to) else {
                continue;
            };
            reached.insert(delivery.to);
            self.sessions[session].send(ServerFrame::Line {
                tick: delivery.tick,
                key: delivery.line.key.clone(),
                params: delivery.line.params.clone(),
                text: self.lexicon.render(&delivery.line),
            });
        }
        for character in reached {
            self.sessions[&by_character[&character]].send(state(world, character));
        }
    }
}

/// Whether an actor in the world already has this name, in any case.
fn name_in_use(world: &World, name: &str) -> bool {
    world
        .entities_with(Actor::NAME)
        .into_iter()
        .filter_map(|id| world.name_of(id))
        .any(|n| n.eq_ignore_ascii_case(name))
}

fn state(world: &World, character: EntityId) -> ServerFrame {
    let here = world.get::<Located>(character).map(|l| l.within);
    let place = here.map(|p| {
        let described = world.get::<Describable>(p);
        PlaceView {
            id: p.0,
            name: described.map(|d| d.name.clone()).unwrap_or_default(),
            description: described.map(|d| d.description.clone()).unwrap_or_default(),
        }
    });
    let exits = here
        .map(|p| {
            world
                .links_from(p)
                .into_iter()
                .map(|(_, l)| l.label)
                .collect()
        })
        .unwrap_or_default();
    let others = here
        .map(|p| {
            world
                .contents(p)
                .into_iter()
                .filter(|id| *id != character)
                .filter_map(|id| world.name_of(id))
                .collect()
        })
        .unwrap_or_default();
    ServerFrame::State {
        tick: world.tick(),
        place,
        exits,
        here: others,
    }
}
