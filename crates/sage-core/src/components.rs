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

/// Marks an entity that can submit commands and perceive occurrences: a player's character
/// or a synthetic agent. Both use exactly the same path.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Actor {}

impl Component for Actor {
    const NAME: &'static str = "sage.actor";
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

/// Where an entity came from: the installed fragment it was placed from. Kept so a world can
/// say which fragments its entities depend on; removing a fragment never rewrites history.
#[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Origin {
    /// Fragment id, `creator.slug`.
    pub fragment: String,
    /// Exact fragment version.
    pub version: String,
    /// The fragment's content digest, `sha256:` and 64 hex digits.
    pub digest: String,
}

impl Component for Origin {
    const NAME: &'static str = "sage.origin";
    const VERSION: u32 = 1;

    fn validate(&self) -> Result<(), String> {
        let hex = self.digest.strip_prefix("sha256:").unwrap_or_default();
        if hex.len() != 64
            || !hex
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err("digest must be `sha256:` and 64 lowercase hex digits".into());
        }
        if self.fragment.len() > 104 || !self.fragment.contains('.') {
            return Err("fragment must be a `creator.slug` id".into());
        }
        if self.version.is_empty() || self.version.len() > 64 {
            return Err("version must be 1 to 64 characters".into());
        }
        Ok(())
    }
}
