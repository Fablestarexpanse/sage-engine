//! Core components. Only what every world needs: a name, being a place, being inside something,
//! and a way between places. Anything genre-specific is a fragment.

use serde::{Deserialize, Serialize};

use crate::component::Component;
use crate::world::EntityId;

/// A name and a description a player can read.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Describable {
    /// Short name.
    pub name: String,
    /// Longer description.
    pub description: String,
}

impl Component for Describable {
    const NAME: &'static str = "sage.describable";
    const VERSION: u32 = 1;
}

/// Marks an entity as a node in the space graph.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Place {}

impl Component for Place {
    const NAME: &'static str = "sage.place";
    const VERSION: u32 = 1;
}

/// Containment: this entity is inside `within`. Containment never forms a cycle.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Located {
    /// The containing entity.
    pub within: EntityId,
}

impl Component for Located {
    const NAME: &'static str = "sage.located";
    const VERSION: u32 = 1;

    fn references(&self) -> Vec<EntityId> {
        vec![self.within]
    }
}

/// A one-way edge in the space graph, carried by its own entity so a way between places can
/// have a description and fragment components (doors, locks, costs) of its own. A two-way
/// passage is two links.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Link {
    /// Where the link starts.
    pub from: EntityId,
    /// Where it leads.
    pub to: EntityId,
    /// What a traveller names to take it, e.g. `north` or `ladder`. Player-facing wording is
    /// the world's business; the engine only matches it.
    pub label: String,
}

impl Component for Link {
    const NAME: &'static str = "sage.link";
    const VERSION: u32 = 1;

    fn references(&self) -> Vec<EntityId> {
        vec![self.from, self.to]
    }
}
