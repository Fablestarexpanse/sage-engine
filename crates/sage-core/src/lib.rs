//! Entities, components, the containment/space graph, the event bus and the scheduler.
//! Genre-agnostic: nothing about any setting belongs here.
//!
//! The event log is the only source of truth. [`World`] is a projection of it, and the only
//! way to change a world is [`Journal::commit`], which checks a batch of events, appends it to
//! an [`EventLog`], then applies it. The [`Scheduler`] advances world time and runs [`System`]s
//! in a fixed order.

mod command;
mod component;
mod components;
mod event;
mod journal;
mod lexicon;
mod perception;
mod scheduler;
mod space;
mod upcast;
mod world;

pub use command::{
    CommandHandler, CommandOutcome, CommandReport, CommandResult, Commands, CoreCommands,
    occurrence,
};
pub use component::{Component, ComponentRegistry};
pub use components::{Actor, Describable, Link, Located, Place};
pub use event::{
    ClockAdvanced, ComponentRemoved, ComponentSet, DecodeError, EntityCreated, EntityDestroyed,
    Event, EventPayload, EventRecord, Occurred,
};
pub use journal::{EventLog, Journal, JournalError, REPLAY_PAGE, StoredEvent, StoredSnapshot};
pub use lexicon::{Lexicon, Line, UNKNOWN_NAME};
pub use perception::Delivery;
pub use scheduler::{Scheduler, StepReport, System, SystemRefused, SystemSuspended};
pub use upcast::{UpcastError, Upcasters};
pub use world::{
    ApplyError, EntityId, SNAPSHOT_SCHEMA_VERSION, Snapshot, SnapshotComponent, SnapshotEntity,
    SnapshotError, World, entities_to_events,
};
