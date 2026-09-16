//! Who perceives an occurrence, and what they are shown. Deterministic: the same log always
//! produces the same perceptions, which is what lets agent memory be a projection of the log.

use serde_json::Value;

use crate::components::{Actor, Describable, Located};
use crate::event::Occurred;
use crate::lexicon::Line;
use crate::world::{EntityId, World};

/// Something an actor perceives or is told.
#[derive(Clone, Debug, PartialEq)]
pub struct Delivery {
    /// The actor it is for.
    pub to: EntityId,
    /// Tick it happened.
    pub tick: u64,
    /// What to show.
    pub line: Line,
    /// The occurrence behind it, if it came from one; absent for private command output.
    pub occurred: Option<Occurred>,
}

impl World {
    /// The display name of an entity, if it has one.
    pub fn name_of(&self, id: EntityId) -> Option<String> {
        self.get::<Describable>(id).map(|d| d.name.clone())
    }

    /// Whether `observer` perceives `occurred` in the world's current state: it is the actor,
    /// one of the targets, or an actor inside one of the listed places.
    pub fn perceives(&self, observer: EntityId, occurred: &Occurred) -> bool {
        if occurred.actor == Some(observer) || occurred.targets.contains(&observer) {
            return true;
        }
        self.get::<Actor>(observer).is_some()
            && self
                .get::<Located>(observer)
                .is_some_and(|l| occurred.places.contains(&l.within))
    }

    /// Every actor that perceives `occurred`, in id order.
    pub fn audience(&self, occurred: &Occurred) -> Vec<EntityId> {
        let mut audience: Vec<EntityId> = occurred
            .actor
            .into_iter()
            .chain(occurred.targets.iter().copied())
            .chain(
                occurred
                    .places
                    .iter()
                    .flat_map(|place| self.contents(*place))
                    .filter(|id| self.get::<Actor>(*id).is_some()),
            )
            .filter(|id| self.contains(*id))
            .collect();
        audience.sort();
        audience.dedup();
        audience
    }

    /// The line `observer` is shown for `occurred`. The key is `<kind>.self` for the actor,
    /// `<kind>.target` for a target, and `<kind>.other.<n>` for someone in the `n`th listed
    /// place. Parameters: `actor`, `target` (the first target) and every top-level string or
    /// number in the data.
    pub fn describe(&self, observer: EntityId, occurred: &Occurred) -> Line {
        let role = if occurred.actor == Some(observer) {
            "self".to_owned()
        } else if occurred.targets.contains(&observer) {
            "target".to_owned()
        } else {
            let here = self.get::<Located>(observer).map(|l| l.within);
            let index = occurred
                .places
                .iter()
                .position(|place| Some(*place) == here)
                .unwrap_or(0);
            format!("other.{index}")
        };
        let mut line = Line::new(format!("{}.{role}", occurred.kind));
        if let Some(name) = occurred.actor.and_then(|a| self.name_of(a)) {
            line = line.with("actor", name);
        }
        if let Some(name) = occurred.targets.first().and_then(|t| self.name_of(*t)) {
            line = line.with("target", name);
        }
        if let Value::Object(fields) = &occurred.data {
            for (name, value) in fields {
                match value {
                    Value::String(s) => line = line.with(name, s),
                    Value::Number(n) => line = line.with(name, n.to_string()),
                    _ => {}
                }
            }
        }
        line
    }

    /// Deliveries for every occurrence in `events` (as stored, with audiences filled in), in
    /// event order then audience order.
    pub fn deliveries_for(&self, tick: u64, events: &[crate::Event]) -> Vec<Delivery> {
        events
            .iter()
            .filter_map(|event| match event {
                crate::Event::Occurred(occurred) => Some(occurred),
                _ => None,
            })
            .flat_map(|occurred| {
                occurred.audience.iter().copied().map(move |to| Delivery {
                    to,
                    tick,
                    line: self.describe(to, occurred),
                    occurred: Some(occurred.clone()),
                })
            })
            .collect()
    }
}
