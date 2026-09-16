//! Typed, versioned components and the registry that lets events name them.

use std::collections::BTreeMap;

use bevy_ecs::world::{EntityRef, EntityWorldMut};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;

use crate::components::{Describable, Located, Place};

/// Data attached to an entity. Every component has a stable name and a schema version, because
/// component data is persisted in events and snapshots.
pub trait Component:
    bevy_ecs::component::Component + Serialize + DeserializeOwned + Clone + Send + Sync + 'static
{
    /// Stable name used in events and snapshots, e.g. `sage.describable`.
    const NAME: &'static str;
    /// Schema version of the serialized data. Starts at 1.
    const VERSION: u32;
}

pub(crate) struct Entry {
    pub(crate) version: u32,
    pub(crate) check: fn(Value) -> Result<(), serde_json::Error>,
    pub(crate) insert: fn(&mut EntityWorldMut, Value) -> Result<(), serde_json::Error>,
    pub(crate) remove: fn(&mut EntityWorldMut),
    pub(crate) read: fn(&EntityRef) -> Option<Value>,
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
        registry
    }

    /// Registers `C`. Panics if another component already uses the same name, since that is a
    /// programming error that would corrupt persisted data.
    pub fn register<C: Component>(&mut self) {
        let entry = Entry {
            version: C::VERSION,
            check: check::<C>,
            insert: insert::<C>,
            remove: remove::<C>,
            read: read::<C>,
        };
        if self.entries.insert(C::NAME, entry).is_some() {
            panic!("component name `{}` registered twice", C::NAME);
        }
    }

    pub(crate) fn get(&self, name: &str) -> Option<&Entry> {
        self.entries.get(name)
    }

    pub(crate) fn iter(&self) -> impl Iterator<Item = (&'static str, &Entry)> {
        self.entries.iter().map(|(name, entry)| (*name, entry))
    }
}

fn check<C: Component>(data: Value) -> Result<(), serde_json::Error> {
    serde_json::from_value::<C>(data).map(|_| ())
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
