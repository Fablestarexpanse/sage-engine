//! Typed, versioned components and the registry that lets events name them.

use std::collections::BTreeMap;

use bevy_ecs::world::{EntityRef, EntityWorldMut};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;

use crate::components::{Actor, Describable, Link, Located, Place};
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

    /// Rules the data must follow beyond its shape. A world refuses a component that fails,
    /// exactly as it refuses data that does not deserialize.
    fn validate(&self) -> Result<(), String> {
        Ok(())
    }
}

/// Converts a component's stored data from version `n` to `n + 1`.
pub type ComponentUpcastFn = fn(Value) -> Result<Value, String>;

pub(crate) struct Entry {
    pub(crate) version: u32,
    /// Steps from older versions, keyed by the version they convert from.
    pub(crate) upcasters: BTreeMap<u32, ComponentUpcastFn>,
    /// Parses data and returns its references, without touching the world.
    pub(crate) parse: fn(Value) -> Result<Vec<EntityId>, String>,
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
        registry.register::<Actor>();
        registry
    }

    /// Registers `C`. Panics if another component already uses the same name, since that is a
    /// programming error that would corrupt persisted data.
    pub fn register<C: Component>(&mut self) {
        let entry = Entry {
            version: C::VERSION,
            upcasters: BTreeMap::new(),
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

    /// Registers how to convert `C`'s stored data from version `from` to `from + 1`, so events
    /// and snapshots written before `C` changed still apply. Stored data is never rewritten.
    /// Panics if `C` is not registered or `from` is not older than its current version.
    pub fn register_upcaster<C: Component>(&mut self, from: u32, step: ComponentUpcastFn) {
        let entry = self
            .entries
            .get_mut(C::NAME)
            .unwrap_or_else(|| panic!("component `{}` is not registered", C::NAME));
        assert!(
            from >= 1 && from < entry.version,
            "`{}` upcaster from v{from} is not below v{}",
            C::NAME,
            entry.version
        );
        entry.upcasters.insert(from, step);
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

fn parse<C: Component>(data: Value) -> Result<Vec<EntityId>, String> {
    let component: C = serde_json::from_value(data).map_err(|e| e.to_string())?;
    component.validate()?;
    Ok(component.references())
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
