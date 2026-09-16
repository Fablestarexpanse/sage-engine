//! Entities, components, the containment/space graph, the event bus and the scheduler.
//! Genre-agnostic: nothing about any setting belongs here.
//!
//! The event log is the only source of truth. [`World`] is a projection of it, and the only
//! way to change a world is [`Journal::commit`], which checks a batch of events, appends it to
//! an [`EventLog`], then applies it.

mod component;
mod components;
mod event;
mod journal;
mod upcast;
mod world;

pub use component::{Component, ComponentRegistry};
pub use components::{Describable, Located, Place};
pub use event::{
    ComponentRemoved, ComponentSet, DecodeError, EntityCreated, EntityDestroyed, Event,
    EventPayload, EventRecord,
};
pub use journal::{EventLog, Journal, JournalError, StoredEvent, StoredSnapshot};
pub use upcast::{UpcastError, Upcasters};
pub use world::{
    ApplyError, EntityId, SNAPSHOT_SCHEMA_VERSION, Snapshot, SnapshotComponent, SnapshotEntity,
    SnapshotError, World,
};
