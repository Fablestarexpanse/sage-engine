//! Core components. Only what every world needs: a name, being a place, and being inside
//! something. Anything genre-specific is a fragment.

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

/// Containment: this entity is inside `within`.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Located {
    /// The containing entity.
    pub within: EntityId,
}

impl Component for Located {
    const NAME: &'static str = "sage.located";
    const VERSION: u32 = 1;
}
