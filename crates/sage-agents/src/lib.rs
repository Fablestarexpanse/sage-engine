//! Synthetic agents: entities with a [`Mind`] that act through the same commands players type.
//!
//! An agent is an ordinary entity with `sage.actor` and `sage.mind`. [`Agents`] collects what
//! each agent perceives, and every `think_every` ticks asks the agent's driver for at most one
//! command, which the caller submits with `Scheduler::submit`. No agent has a private API: it
//! can do only what a player in its place could do.
//!
//! Drivers: `scripted` (zero-AI, rules as data), `hybrid` (rules that may `@think`), and `llm`.
//! Without a configured model, `@think` rules are skipped and `llm` agents stay idle, so every
//! world still runs with no AI.

pub mod llm;
mod memory;
mod mind;
pub mod retrieval;
mod scripted;

use sage_core::{
    Actor, ComponentRegistry, EntityId, EventLog, Lexicon, Located, StepReport, Upcasters, World,
};

use llm::{Allowed, ThinkError, Thinker};
use scripted::Action;

pub use memory::{MEMORY_LIMIT, Memories, Memory};
pub use mind::{Mind, Rule, When};

/// The core components plus `sage.mind`: the registry every SAGE world with agents uses.
pub fn registry() -> ComponentRegistry {
    let mut registry = ComponentRegistry::with_core();
    registry.register::<Mind>();
    registry.register_upcaster::<Mind>(1, mind::mind_v1_to_v2);
    registry
}

/// Where a thought came from.
#[derive(Clone, Debug, PartialEq)]
pub enum Source {
    /// A scripted rule, by index.
    Rule(usize),
    /// The model.
    Model,
}

/// A command an agent decided on.
#[derive(Clone, Debug, PartialEq)]
pub struct Thought {
    /// The agent.
    pub agent: EntityId,
    /// Command text, exactly as a player would type it.
    pub command: String,
    /// What produced it.
    pub source: Source,
}

/// Model answers gathered on one tick.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Collected {
    /// Commands to submit.
    pub thoughts: Vec<Thought>,
    /// Answers that produced nothing: refused, unreachable, or too late.
    pub failed: Vec<(EntityId, String)>,
}

/// Runs every agent's mind.
pub struct Agents {
    memories: Memories,
    thinker: Option<Thinker>,
    lexicon: Lexicon,
    verbs: Vec<String>,
}

impl Default for Agents {
    fn default() -> Agents {
        Agents {
            memories: Memories::new(),
            thinker: None,
            lexicon: Lexicon::core_english(),
            verbs: Vec::new(),
        }
    }
}

impl Agents {
    /// No memories yet: for a new world.
    pub fn new() -> Agents {
        Agents::default()
    }

    /// Agents whose memories are rebuilt from `log`: for an existing world.
    pub fn rebuild<L: EventLog>(log: &L, upcasters: &Upcasters) -> Result<Agents, String> {
        Ok(Agents {
            memories: Memories::rebuild(log, upcasters)?,
            ..Agents::default()
        })
    }

    /// Lets `llm` and `hybrid` agents ask a model through `thinker`.
    pub fn with_thinker(mut self, thinker: Thinker) -> Agents {
        self.thinker = Some(thinker);
        self
    }

    /// The wording used to show a model what its agent perceived.
    pub fn with_lexicon(mut self, lexicon: Lexicon) -> Agents {
        self.lexicon = lexicon;
        self
    }

    /// The verbs a model may use; normally every verb registered with the scheduler.
    pub fn with_verbs(mut self, verbs: Vec<String>) -> Agents {
        self.verbs = verbs;
        self
    }

    /// Records a step's occurrences in the memory of everyone who perceived them.
    pub fn observe(&mut self, report: &StepReport) {
        self.memories.observe(report);
    }

    /// Every actor's memories.
    pub fn memories(&self) -> &Memories {
        &self.memories
    }

    /// Lets every agent due at `tick` think, in id order, and returns commands decided by
    /// rules. Model requests are sent in the background; collect their answers with
    /// [`Agents::collect`].
    ///
    /// An agent is due when `(tick + id) % think_every == 0`, which staggers agents with the
    /// same interval. Rules consider what the agent perceived since its previous scheduled
    /// think: ticks `tick - think_every` to `tick - 1`. That window depends only on the log and
    /// the tick, so a restarted world's rules decide exactly as an uninterrupted world's.
    pub fn think(&mut self, world: &World, tick: u64) -> Vec<Thought> {
        let mut thoughts = Vec::new();
        for agent in world.entities_with(<Mind as sage_core::Component>::NAME) {
            if world.get::<Actor>(agent).is_none() {
                continue;
            }
            let mind = world.get::<Mind>(agent).expect("listed by entities_with");
            if tick == 0 || !(tick + agent.0).is_multiple_of(mind.think_every) {
                continue;
            }
            let can_think = self
                .thinker
                .as_ref()
                .is_some_and(|thinker| thinker.available(agent, tick));
            let decision = match mind.driver.as_str() {
                "scripted" | "hybrid" => {
                    let recent = self.memories.between(
                        agent,
                        tick.saturating_sub(mind.think_every),
                        tick - 1,
                    );
                    scripted::decide(
                        world,
                        agent,
                        mind,
                        &recent,
                        tick,
                        can_think && mind.driver == "hybrid",
                    )
                }
                "llm" if can_think => Some((usize::MAX, Action::Think)),
                _ => None,
            };
            match decision {
                Some((rule, Action::Command(command))) => thoughts.push(Thought {
                    agent,
                    command,
                    source: Source::Rule(rule),
                }),
                Some((_, Action::Think)) => self.ask(world, agent, mind, tick),
                None => {}
            }
        }
        thoughts
    }

    fn ask(&mut self, world: &World, agent: EntityId, mind: &Mind, tick: u64) {
        let exits = world
            .get::<Located>(agent)
            .map(|l| {
                world
                    .links_from(l.within)
                    .into_iter()
                    .map(|(_, link)| link.label)
                    .collect()
            })
            .unwrap_or_default();
        let allowed = Allowed {
            verbs: self.verbs.clone(),
            exits,
        };
        let memories: Vec<&Memory> = self.memories.of(agent).collect();
        let parts =
            llm::PromptParts::gather(world, agent, mind, &memories, &allowed, &self.lexicon, tick);
        self.thinker
            .as_mut()
            .expect("asked only when a thinker is available")
            .ask(agent, tick, parts, allowed);
    }

    /// Model answers that have arrived, as commands for `tick`. Answers to requests made more
    /// than [`llm::MAX_ANSWER_AGE`] ticks ago are dropped, as are answers for agents that are
    /// no longer actors.
    pub fn collect(&mut self, world: &World, tick: u64) -> Collected {
        let mut collected = Collected::default();
        let Some(thinker) = self.thinker.as_mut() else {
            return collected;
        };
        for answer in thinker.collect(tick) {
            let agent = answer.agent;
            let command = match answer.result {
                Err(ThinkError::Unreachable(reason)) => {
                    collected
                        .failed
                        .push((agent, format!("unreachable: {reason}")));
                    continue;
                }
                Err(ThinkError::Refused(reason)) => {
                    collected.failed.push((agent, format!("refused: {reason}")));
                    continue;
                }
                Ok(None) => continue,
                Ok(Some(command)) => command,
            };
            if tick.saturating_sub(answer.tick) > llm::MAX_ANSWER_AGE {
                collected.failed.push((
                    agent,
                    format!("answer arrived {} ticks late", tick - answer.tick),
                ));
                continue;
            }
            if world.get::<Actor>(agent).is_none() {
                collected.failed.push((agent, "no longer an actor".into()));
                continue;
            }
            collected.thoughts.push(Thought {
                agent,
                command,
                source: Source::Model,
            });
        }
        collected
    }
}
