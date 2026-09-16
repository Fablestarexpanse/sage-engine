//! Synthetic agents: entities with a [`Mind`] that act through the same commands players type.
//!
//! An agent is an ordinary entity with `sage.actor` and `sage.mind`. [`Agents`] collects what
//! each agent perceives, and every `think_every` ticks asks the agent's driver for at most one
//! command, which the caller submits with `Scheduler::submit`. No agent has a private API: it
//! can do only what a player in its place could do.
//!
//! Drivers: `scripted` (zero-AI, rules as data). LLM and hybrid drivers arrive in M3 S3.

mod mind;
mod scripted;

use std::collections::BTreeMap;

use sage_core::{Actor, ComponentRegistry, Delivery, EntityId, StepReport, World};

pub use mind::{Mind, Rule, When};

/// Most perceptions kept per agent between thinks; older ones are dropped first.
pub const INBOX_LIMIT: usize = 64;

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
    inboxes: BTreeMap<EntityId, Vec<Delivery>>,
}

impl Agents {
    /// No perceptions yet.
    pub fn new() -> Agents {
        Agents::default()
    }

    /// Keeps each delivery addressed to an agent until that agent next thinks.
    pub fn observe(&mut self, world: &World, report: &StepReport) {
        for delivery in &report.deliveries {
            if world.get::<Mind>(delivery.to).is_none() {
                continue;
            }
            let inbox = self.inboxes.entry(delivery.to).or_default();
            inbox.push(delivery.clone());
            if inbox.len() > INBOX_LIMIT {
                inbox.remove(0);
            }
        }
    }

    /// Perceptions waiting for `agent`.
    pub fn inbox(&self, agent: EntityId) -> &[Delivery] {
        self.inboxes
            .get(&agent)
            .map(Vec::as_slice)
            .unwrap_or_default()
    }

    /// Lets every agent due at `tick` think, in id order, and returns their commands for that
    /// tick. An agent is due when `(tick + id) % think_every == 0`, which staggers agents with
    /// the same interval. A thinking agent's inbox is emptied whether or not it acts.
    pub fn think(&mut self, world: &World, tick: u64) -> Vec<Thought> {
        let mut thoughts = Vec::new();
        for agent in world.entities_with(<Mind as sage_core::Component>::NAME) {
            if world.get::<Actor>(agent).is_none() {
                continue;
            }
            let mind = world.get::<Mind>(agent).expect("listed by entities_with");
            if !(tick + agent.0).is_multiple_of(mind.think_every) {
                continue;
            }
            let inbox = self.inboxes.remove(&agent).unwrap_or_default();
            let decision = match mind.driver.as_str() {
                "scripted" => scripted::decide(world, agent, mind, &inbox, tick),
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
