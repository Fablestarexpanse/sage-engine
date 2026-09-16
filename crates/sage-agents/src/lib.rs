//! Synthetic agents: entities with a [`Mind`] that act through the same commands players type.
//!
//! An agent is an ordinary entity with `sage.actor` and `sage.mind`. [`Agents`] collects what
//! each agent perceives, and every `think_every` ticks asks the agent's driver for at most one
//! command, which the caller submits with `Scheduler::submit`. No agent has a private API: it
//! can do only what a player in its place could do.
//!
//! Drivers: `scripted` (zero-AI, rules as data). LLM and hybrid drivers arrive in M3 S3.

mod memory;
mod mind;
mod scripted;

use sage_core::{Actor, ComponentRegistry, EntityId, EventLog, StepReport, Upcasters, World};

pub use memory::{MEMORY_LIMIT, Memories, Memory};
pub use mind::{Mind, Rule, When};

/// The core components plus `sage.mind`: the registry every SAGE world with agents uses.
pub fn registry() -> ComponentRegistry {
    let mut registry = ComponentRegistry::with_core();
    registry.register::<Mind>();
    registry
}

/// A command an agent decided on.
#[derive(Clone, Debug, PartialEq)]
pub struct Thought {
    /// The agent.
    pub agent: EntityId,
    /// Command text, exactly as a player would type it.
    pub command: String,
    /// Index of the rule that produced it.
    pub rule: usize,
}

/// Runs every agent's mind.
#[derive(Default)]
pub struct Agents {
    memories: Memories,
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
        })
    }

    /// Records a step's occurrences in the memory of everyone who perceived them.
    pub fn observe(&mut self, report: &StepReport) {
        self.memories.observe(report);
    }

    /// Every actor's memories.
    pub fn memories(&self) -> &Memories {
        &self.memories
    }

    /// Lets every agent due at `tick` think, in id order, and returns their commands for that
    /// tick. An agent is due when `(tick + id) % think_every == 0`, which staggers agents with
    /// the same interval. It considers what it perceived since its previous scheduled think:
    /// ticks `tick - think_every` to `tick - 1`. That window depends only on the log and the
    /// tick, so a restarted world thinks exactly as an uninterrupted one.
    pub fn think(&mut self, world: &World, tick: u64) -> Vec<Thought> {
        let mut thoughts = Vec::new();
        for agent in world.entities_with(<Mind as sage_core::Component>::NAME) {
            if world.get::<Actor>(agent).is_none() {
                continue;
            }
            let mind = world.get::<Mind>(agent).expect("listed by entities_with");
            if !(tick + agent.0).is_multiple_of(mind.think_every) || tick == 0 {
                continue;
            }
            let recent =
                self.memories
                    .between(agent, tick.saturating_sub(mind.think_every), tick - 1);
            let decision = match mind.driver.as_str() {
                "scripted" => scripted::decide(world, agent, mind, &recent, tick),
                _ => None,
            };
            if let Some((rule, command)) = decision {
                thoughts.push(Thought {
                    agent,
                    command,
                    rule,
                });
            }
        }
        thoughts
    }
}
