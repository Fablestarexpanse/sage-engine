//! Typed, versioned components and the registry that lets events name them.

use std::collections::BTreeMap;

use bevy_ecs::world::{EntityRef, EntityWorldMut};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;

use crate::components::{Describable, Link, Located, Place};
use crate::world::EntityId;

/// Data attached to an entity. Every component has a stable name and a schema version, because
/// component data is persisted in events and snapshots.
pub trait Component:
    bevy_ecs::component::Component + Serialize + DeserializeOwned + Clone + Send + Sync + 'static
{
    /// Stable name used in events and snapshots, e.g. `sage.describable`.
    const NAME: &'static str;
    /// Schema version of the serialized data. Starts at 1.
    const VERSION: u32;

    /// Entities this component points at. A world refuses to set a component whose references
    /// are not live entities, and refuses to destroy an entity something still references.
    fn references(&self) -> Vec<EntityId> {
        Vec::new()
    }
}

pub(crate) struct Entry {
    pub(crate) version: u32,
    /// Parses data and returns its references, without touching the world.
    pub(crate) parse: fn(Value) -> Result<Vec<EntityId>, serde_json::Error>,
    pub(crate) insert: fn(&mut EntityWorldMut, Value) -> Result<(), serde_json::Error>,
    pub(crate) remove: fn(&mut EntityWorldMut),
    pub(crate) read: fn(&EntityRef) -> Option<Value>,
    pub(crate) read_references: fn(&EntityRef) -> Vec<EntityId>,
}

/// Maps component names to their Rust types. A world only accepts components that are
/// registered, at exactly the registered version.
#[derive(Default)]
pub struct ComponentRegistry {
    entries: BTreeMap<&'static str, Entry>,
}

impl ComponentRegistry {
    /// An empty registry.
    pub fn new() -> Self {
        Self::default()
    }

    /// A registry holding the engine's core components.
    pub fn with_core() -> Self {
        let mut registry = Self::new();
        registry.register::<Describable>();
        registry.register::<Place>();
        registry.register::<Located>();
        registry.register::<Link>();
        registry
    }

    /// Registers `C`. Panics if another component already uses the same name, since that is a
    /// programming error that would corrupt persisted data.
    pub fn register<C: Component>(&mut self) {
        let entry = Entry {
            version: C::VERSION,
            parse: parse::<C>,
            insert: insert::<C>,
            remove: remove::<C>,
            read: read::<C>,
            read_references: read_references::<C>,
        };
        if self.entries.insert(C::NAME, entry).is_some() {
            panic!("component name `{}` registered twice", C::NAME);
        }
    }

    pub(crate) fn get(&self, name: &str) -> Option<(&'static str, &Entry)> {
        self.entries
            .get_key_value(name)
            .map(|(name, entry)| (*name, entry))
    }

    pub(crate) fn iter(&self) -> impl Iterator<Item = (&'static str, &Entry)> {
        self.entries.iter().map(|(name, entry)| (*name, entry))
    }
}

fn parse<C: Component>(data: Value) -> Result<Vec<EntityId>, serde_json::Error> {
    serde_json::from_value::<C>(data).map(|c| c.references())
}

fn insert<C: Component>(entity: &mut EntityWorldMut, data: Value) -> Result<(), serde_json::Error> {
    let component: C = serde_json::from_value(data)?;
    entity.insert(component);
    Ok(())
}

fn remove<C: Component>(entity: &mut EntityWorldMut) {
    entity.remove::<C>();
}

fn read<C: Component>(entity: &EntityRef) -> Option<Value> {
    entity.get::<C>().map(|component| {
        serde_json::to_value(component).expect("registered components serialize to JSON")
    })
}

fn read_references<C: Component>(entity: &EntityRef) -> Vec<EntityId> {
    entity
        .get::<C>()
        .map(Component::references)
        .unwrap_or_default()
}
