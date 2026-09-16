//! The world: a projection of the event log onto a `bevy_ecs` world.
//!
//! A batch of events is applied for real, one event at a time, and every step records how to
//! undo itself. If any event is refused, or the log then refuses the append, the steps are
//! undone in reverse. Rules are checked against the real world state, so there is one
//! implementation of each rule, not a checker and an applier that could disagree.

use std::collections::BTreeMap;

use bevy_ecs::entity::Entity;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

use crate::component::ComponentRegistry;
use crate::components::Located;
use crate::event::{ComponentRemoved, ComponentSet, EntityCreated, EntityDestroyed, Event};

/// Stable entity identity. Stored in events and snapshots; never reused.
#[derive(
    bevy_ecs::component::Component,
    Serialize,
    Deserialize,
    Clone,
    Copy,
    Debug,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
    Hash,
)]
#[serde(transparent)]
pub struct EntityId(pub u64);

/// Schema version of [`Snapshot`].
pub const SNAPSHOT_SCHEMA_VERSION: u32 = 1;

/// Why an event cannot be applied. Nothing is written when this happens.
#[derive(Clone, Debug, Error, PartialEq)]
pub enum ApplyError {
    /// `EntityCreated` for an id that exists or once existed.
    #[error("entity {0:?} already exists or was used before")]
    IdReused(EntityId),
    /// The event targets an entity that does not exist.
    #[error("no entity {0:?}")]
    NoSuchEntity(EntityId),
    /// The component name is not registered.
    #[error("component `{0}` is not registered")]
    UnknownComponent(String),
    /// The event's component version differs from the registered one.
    #[error("component `{component}` is v{registered} but the event carries v{found}")]
    ComponentVersion {
        /// Component name.
        component: String,
        /// Registered version.
        registered: u32,
        /// Version in the event.
        found: u32,
    },
    /// The component data does not deserialize.
    #[error("component `{component}` data is invalid: {reason}")]
    ComponentData {
        /// Component name.
        component: String,
        /// Deserialization error.
        reason: String,
    },
    /// A component points at an entity that does not exist.
    #[error("component `{component}` points at missing entity {target:?}")]
    DanglingReference {
        /// Component name.
        component: String,
        /// Missing entity.
        target: EntityId,
    },
    /// An entity cannot be destroyed while another entity points at it.
    #[error("entity {id:?} is still referenced by `{component}` on {by:?}")]
    StillReferenced {
        /// Entity being destroyed.
        id: EntityId,
        /// Entity holding the reference.
        by: EntityId,
        /// Component holding the reference.
        component: &'static str,
    },
    /// Putting `id` inside `within` would make containment loop.
    #[error("placing {id:?} inside {within:?} would make containment loop")]
    ContainmentCycle {
        /// Entity being placed.
        id: EntityId,
        /// Intended container.
        within: EntityId,
    },
    /// An occurrence is malformed or points at missing entities.
    #[error("occurrence `{kind}` is invalid: {reason}")]
    BadOccurrence {
        /// The occurrence kind as given.
        kind: String,
        /// What is wrong.
        reason: String,
    },
    /// A batch's tick is earlier than the world's.
    #[error("tick {tick} is earlier than the world's tick {current}")]
    TickWentBackwards {
        /// Tick of the batch.
        tick: u64,
        /// World tick.
        current: u64,
    },
}

/// Why a snapshot cannot be restored.
#[derive(Debug, Error)]
pub enum SnapshotError {
    /// The snapshot bytes are not valid JSON for [`Snapshot`].
    #[error("snapshot is not readable: {0}")]
    Malformed(#[from] serde_json::Error),
    /// The snapshot format version is not one this engine reads.
    #[error("snapshot format v{0} is not supported (this engine reads v{SNAPSHOT_SCHEMA_VERSION})")]
    Version(u32),
    /// The snapshot's contents fail the same rules events do.
    #[error("snapshot content is invalid: {0}")]
    Content(#[from] ApplyError),
    /// Entities in the snapshot are not sorted by id.
    #[error("snapshot entities are not in id order at {0:?}")]
    Unordered(EntityId),
}

/// Full world state at one point in the log, in a canonical, byte-stable form: entities sorted
/// by id, components sorted by name, JSON object keys sorted.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Snapshot {
    /// Format version, [`SNAPSHOT_SCHEMA_VERSION`].
    pub schema_version: u32,
    /// Sequence number of the last event included.
    pub last_seq: u64,
    /// Tick of the last event included.
    pub tick: u64,
    /// Next id [`World::next_entity_id`] hands out.
    pub next_entity_id: u64,
    /// Every live entity.
    pub entities: Vec<SnapshotEntity>,
}

/// One entity in a [`Snapshot`].
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct SnapshotEntity {
    /// Entity id.
    pub id: EntityId,
    /// Components by name.
    pub components: BTreeMap<String, SnapshotComponent>,
}

/// One component in a [`Snapshot`].
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct SnapshotComponent {
    /// Component schema version.
    pub version: u32,
    /// Serialized component.
    pub data: Value,
}

impl Snapshot {
    /// Canonical bytes. Two worlds in the same state produce identical bytes.
    pub fn to_bytes(&self) -> Vec<u8> {
        serde_json::to_vec(self).expect("snapshots serialize to JSON")
    }

    /// Parses bytes produced by [`Snapshot::to_bytes`].
    pub fn from_bytes(bytes: &[u8]) -> Result<Snapshot, SnapshotError> {
        let snapshot: Snapshot = serde_json::from_slice(bytes)?;
        if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION {
            return Err(SnapshotError::Version(snapshot.schema_version));
        }
        Ok(snapshot)
    }
}

enum UndoStep {
    Created(EntityId),
    Destroyed {
        id: EntityId,
        components: Vec<(&'static str, Value)>,
    },
    Component {
        id: EntityId,
        name: &'static str,
        previous: Option<Value>,
    },
}

/// How to take back an applied batch.
pub(crate) struct Undo {
    steps: Vec<UndoStep>,
    last_seq: u64,
    tick: u64,
    next_entity_id: u64,
}

/// Current world state. Read it freely; change it only through [`crate::Journal`].
pub struct World {
    pub(crate) ecs: bevy_ecs::world::World,
    index: BTreeMap<EntityId, Entity>,
    registry: ComponentRegistry,
    next_entity_id: u64,
    last_seq: u64,
    tick: u64,
}

impl World {
    pub(crate) fn empty(registry: ComponentRegistry) -> World {
        World {
            ecs: bevy_ecs::world::World::new(),
            index: BTreeMap::new(),
            registry,
            next_entity_id: 1,
            last_seq: 0,
            tick: 0,
        }
    }

    /// Sequence number of the last applied event (0 for a new world).
    pub fn last_seq(&self) -> u64 {
        self.last_seq
    }

    /// Tick of the last applied event.
    pub fn tick(&self) -> u64 {
        self.tick
    }

    /// The id the next `EntityCreated` should use.
    pub fn next_entity_id(&self) -> EntityId {
        EntityId(self.next_entity_id)
    }

    /// Whether `id` is a live entity.
    pub fn contains(&self, id: EntityId) -> bool {
        self.index.contains_key(&id)
    }

    /// Number of live entities.
    pub fn len(&self) -> usize {
        self.index.len()
    }

    /// Whether the world has no entities.
    pub fn is_empty(&self) -> bool {
        self.index.is_empty()
    }

    /// Reads a component of a live entity.
    pub fn get<C: crate::Component>(&self, id: EntityId) -> Option<&C> {
        let entity = *self.index.get(&id)?;
        self.ecs.get::<C>(entity)
    }

    /// Reads a component by registered name, as the JSON stored in events. For callers that
    /// do not have the Rust type, such as plugins.
    pub fn component_json(&self, id: EntityId, component: &str) -> Option<Value> {
        let entity = *self.index.get(&id)?;
        let (_, entry) = self.registry.get(component)?;
        (entry.read)(&self.ecs.entity(entity))
    }

    /// Live entities carrying the named component, by id. Empty for an unregistered name.
    pub fn entities_with(&self, component: &str) -> Vec<EntityId> {
        let Some((_, entry)) = self.registry.get(component) else {
            return Vec::new();
        };
        self.index
            .iter()
            .filter(|(_, entity)| (entry.read)(&self.ecs.entity(**entity)).is_some())
            .map(|(id, _)| *id)
            .collect()
    }

    /// Applies `events` as `first_seq..` at `tick`. On refusal the world is exactly as before
    /// and the error names the refused event's position.
    pub(crate) fn apply_batch(
        &mut self,
        first_seq: u64,
        tick: u64,
        events: &[Event],
    ) -> Result<Undo, (usize, ApplyError)> {
        debug_assert_eq!(first_seq, self.last_seq + 1, "events apply in sequence");
        if tick < self.tick {
            return Err((
                0,
                ApplyError::TickWentBackwards {
                    tick,
                    current: self.tick,
                },
            ));
        }
        let mut undo = Undo {
            steps: Vec::new(),
            last_seq: self.last_seq,
            tick: self.tick,
            next_entity_id: self.next_entity_id,
        };
        for (i, event) in events.iter().enumerate() {
            if let Err(error) = self.apply_one(event, &mut undo.steps) {
                self.undo(undo);
                return Err((i, error));
            }
        }
        self.last_seq = first_seq + events.len() as u64 - 1;
        self.tick = tick;
        Ok(undo)
    }

    /// Validates one event against the current state, then applies it. Changes nothing when it
    /// returns an error.
    fn apply_one(&mut self, event: &Event, steps: &mut Vec<UndoStep>) -> Result<(), ApplyError> {
        match event {
            Event::EntityCreated(EntityCreated { id }) => {
                if id.0 < self.next_entity_id {
                    return Err(ApplyError::IdReused(*id));
                }
                let entity = self.ecs.spawn(*id).id();
                self.index.insert(*id, entity);
                self.next_entity_id = id.0 + 1;
                steps.push(UndoStep::Created(*id));
            }
            Event::EntityDestroyed(EntityDestroyed { id }) => {
                let entity = self.entity(*id)?;
                if let Some((by, component)) = self.referrer_of(*id) {
                    return Err(ApplyError::StillReferenced {
                        id: *id,
                        by,
                        component,
                    });
                }
                let entity_ref = self.ecs.entity(entity);
                let components = self
                    .registry
                    .iter()
                    .filter_map(|(name, entry)| (entry.read)(&entity_ref).map(|v| (name, v)))
                    .collect();
                self.ecs.despawn(entity);
                self.index.remove(id);
                steps.push(UndoStep::Destroyed {
                    id: *id,
                    components,
                });
            }
            Event::ComponentSet(set) => {
                let entity = self.entity(set.id)?;
                let (name, entry) = self
                    .registry
                    .get(&set.component)
                    .ok_or_else(|| ApplyError::UnknownComponent(set.component.clone()))?;
                let version_error = || ApplyError::ComponentVersion {
                    component: set.component.clone(),
                    registered: entry.version,
                    found: set.component_version,
                };
                if set.component_version == 0 || set.component_version > entry.version {
                    return Err(version_error());
                }
                let mut data = set.data.clone();
                for from in set.component_version..entry.version {
                    let step = entry.upcasters.get(&from).ok_or_else(version_error)?;
                    data = step(data).map_err(|reason| ApplyError::ComponentData {
                        component: set.component.clone(),
                        reason: format!("upcasting from v{from}: {reason}"),
                    })?;
                }
                let references =
                    (entry.parse)(data.clone()).map_err(|reason| ApplyError::ComponentData {
                        component: set.component.clone(),
                        reason,
                    })?;
                if let Some(target) = references.into_iter().find(|t| !self.contains(*t)) {
                    return Err(ApplyError::DanglingReference {
                        component: set.component.clone(),
                        target,
                    });
                }
                if name == <Located as crate::Component>::NAME {
                    let located: Located =
                        serde_json::from_value(data.clone()).expect("parsed above");
                    if self.contains_transitively(set.id, located.within) {
                        return Err(ApplyError::ContainmentCycle {
                            id: set.id,
                            within: located.within,
                        });
                    }
                }
                let previous = (entry.read)(&self.ecs.entity(entity));
                (entry.insert)(&mut self.ecs.entity_mut(entity), data).expect("parsed above");
                steps.push(UndoStep::Component {
                    id: set.id,
                    name,
                    previous,
                });
            }
            Event::ComponentRemoved(ComponentRemoved { id, component }) => {
                let entity = self.entity(*id)?;
                let (name, entry) = self
                    .registry
                    .get(component)
                    .ok_or_else(|| ApplyError::UnknownComponent(component.clone()))?;
                let previous = (entry.read)(&self.ecs.entity(entity));
                (entry.remove)(&mut self.ecs.entity_mut(entity));
                steps.push(UndoStep::Component {
                    id: *id,
                    name,
                    previous,
                });
            }
            Event::ClockAdvanced(_) => {}
            Event::Occurred(occurred) => self.check_occurrence(occurred)?,
        }
        Ok(())
    }

    /// Takes back a batch applied by [`World::apply_batch`].
    pub(crate) fn undo(&mut self, undo: Undo) {
        for step in undo.steps.into_iter().rev() {
            match step {
                UndoStep::Created(id) => {
                    let entity = self.index.remove(&id).expect("undo: created entity exists");
                    self.ecs.despawn(entity);
                }
                UndoStep::Destroyed { id, components } => {
                    let entity = self.ecs.spawn(id).id();
                    self.index.insert(id, entity);
                    for (name, data) in components {
                        let (_, entry) = self.registry.get(name).expect("undo: registered");
                        (entry.insert)(&mut self.ecs.entity_mut(entity), data)
                            .expect("undo: data came from this world");
                    }
                }
                UndoStep::Component { id, name, previous } => {
                    let entity = self.index[&id];
                    let (_, entry) = self.registry.get(name).expect("undo: registered");
                    let mut entity_mut = self.ecs.entity_mut(entity);
                    match previous {
                        Some(data) => (entry.insert)(&mut entity_mut, data)
                            .expect("undo: data came from this world"),
                        None => (entry.remove)(&mut entity_mut),
                    }
                }
            }
        }
        self.last_seq = undo.last_seq;
        self.tick = undo.tick;
        self.next_entity_id = undo.next_entity_id;
    }

    fn check_occurrence(&self, occurred: &crate::event::Occurred) -> Result<(), ApplyError> {
        let bad = |reason: String| ApplyError::BadOccurrence {
            kind: occurred.kind.clone(),
            reason,
        };
        let segments: Vec<&str> = occurred.kind.split('.').collect();
        let well_formed = occurred.kind.len() <= 128
            && segments.len() >= 2
            && segments.iter().all(|s| {
                !s.is_empty()
                    && s.bytes()
                        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
            });
        if !well_formed {
            return Err(bad(
                "kind must be at least two dot-separated lowercase segments".into(),
            ));
        }
        if occurred.kind_version == 0 {
            return Err(bad("kind_version must be at least 1".into()));
        }
        for id in occurred
            .actor
            .iter()
            .chain(&occurred.places)
            .chain(&occurred.targets)
        {
            if !self.contains(*id) {
                return Err(bad(format!("refers to missing entity {id:?}")));
            }
        }
        Ok(())
    }

    fn entity(&self, id: EntityId) -> Result<Entity, ApplyError> {
        self.index
            .get(&id)
            .copied()
            .ok_or(ApplyError::NoSuchEntity(id))
    }

    /// Some live entity other than `id` whose components point at `id`. Scans every entity;
    /// fine at M1 sizes, replace with a reverse index when profiling says so.
    fn referrer_of(&self, id: EntityId) -> Option<(EntityId, &'static str)> {
        self.index
            .iter()
            .filter(|(other, _)| **other != id)
            .find_map(|(other, entity)| {
                let entity_ref = self.ecs.entity(*entity);
                self.registry.iter().find_map(|(name, entry)| {
                    (entry.read_references)(&entity_ref)
                        .contains(&id)
                        .then_some((*other, name))
                })
            })
    }

    /// Whether `id` is `target` or contains it at any depth.
    fn contains_transitively(&self, id: EntityId, target: EntityId) -> bool {
        let mut current = Some(target);
        let mut steps = 0;
        while let Some(at) = current {
            if at == id {
                return true;
            }
            steps += 1;
            assert!(steps <= self.index.len() + 1, "containment already loops");
            current = self.get::<Located>(at).map(|l| l.within);
        }
        false
    }

    pub(crate) fn live_entities(&self) -> impl Iterator<Item = (EntityId, Entity)> + '_ {
        self.index.iter().map(|(id, entity)| (*id, *entity))
    }

    /// The world's full state in canonical form.
    pub fn snapshot(&self) -> Snapshot {
        let entities = self
            .index
            .iter()
            .map(|(id, entity)| {
                let entity_ref = self.ecs.entity(*entity);
                let components = self
                    .registry
                    .iter()
                    .filter_map(|(name, entry)| {
                        (entry.read)(&entity_ref).map(|data| {
                            let component = SnapshotComponent {
                                version: entry.version,
                                data,
                            };
                            (name.to_owned(), component)
                        })
                    })
                    .collect();
                SnapshotEntity {
                    id: *id,
                    components,
                }
            })
            .collect();
        Snapshot {
            schema_version: SNAPSHOT_SCHEMA_VERSION,
            last_seq: self.last_seq,
            tick: self.tick,
            next_entity_id: self.next_entity_id,
            entities,
        }
    }

    /// Rebuilds a world from a snapshot by applying it as events, so it passes every rule an
    /// event would.
    pub(crate) fn restore(
        registry: ComponentRegistry,
        snapshot: &Snapshot,
    ) -> Result<World, SnapshotError> {
        if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION {
            return Err(SnapshotError::Version(snapshot.schema_version));
        }
        for pair in snapshot.entities.windows(2) {
            if pair[0].id >= pair[1].id {
                return Err(SnapshotError::Unordered(pair[1].id));
            }
        }
        if let Some(last) = snapshot.entities.last()
            && last.id.0 >= snapshot.next_entity_id
        {
            return Err(ApplyError::IdReused(last.id).into());
        }

        let events = entities_to_events(&snapshot.entities);

        let mut world = World::empty(registry);
        let mut steps = Vec::new();
        for event in &events {
            world
                .apply_one(event, &mut steps)
                .map_err(SnapshotError::Content)?;
        }
        world.next_entity_id = snapshot.next_entity_id;
        world.last_seq = snapshot.last_seq;
        world.tick = snapshot.tick;
        Ok(world)
    }
}

/// The events that build `entities` into an empty world: every `EntityCreated` first, then
/// components, with containment last so each container's own `Located` is already set when the
/// cycle check walks it. Used by snapshot restore and by world seed files.
pub fn entities_to_events(entities: &[SnapshotEntity]) -> Vec<Event> {
    let mut events: Vec<Event> = entities
        .iter()
        .map(|e| Event::EntityCreated(EntityCreated { id: e.id }))
        .collect();
    // Containment goes last so every container already has its own `Located`, which the
    // cycle check walks.
    let (located, other): (Vec<_>, Vec<_>) = entities
        .iter()
        .flat_map(|e| {
            e.components.iter().map(|(name, c)| {
                Event::ComponentSet(ComponentSet {
                    id: e.id,
                    component: name.clone(),
                    component_version: c.version,
                    data: c.data.clone(),
                })
            })
        })
        .partition(|event| {
            matches!(event, Event::ComponentSet(s) if s.component == <Located as crate::Component>::NAME)
        });
    events.extend(other);
    events.extend(located);
    events
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::{Component, Describable, Link, Located, Place};

    fn created(id: u64) -> Event {
        Event::EntityCreated(EntityCreated { id: EntityId(id) })
    }

    fn destroyed(id: u64) -> Event {
        Event::EntityDestroyed(EntityDestroyed { id: EntityId(id) })
    }

    fn set<C: Component>(id: u64, c: &C) -> Event {
        Event::ComponentSet(ComponentSet {
            id: EntityId(id),
            component: C::NAME.into(),
            component_version: C::VERSION,
            data: serde_json::to_value(c).unwrap(),
        })
    }

    fn within(id: u64) -> Located {
        Located {
            within: EntityId(id),
        }
    }

    fn world() -> World {
        World::empty(ComponentRegistry::with_core())
    }

    fn apply(world: &mut World, events: &[Event]) -> Result<(), (usize, ApplyError)> {
        let seq = world.last_seq() + 1;
        world.apply_batch(seq, 0, events).map(|_| ())
    }

    /// A refused batch leaves the world byte-identical to before.
    fn refused(world: &mut World, events: &[Event]) -> (usize, ApplyError) {
        let before = world.snapshot().to_bytes();
        let err = apply(world, events).err().unwrap();
        assert_eq!(
            world.snapshot().to_bytes(),
            before,
            "refusal changed the world"
        );
        err
    }

    #[test]
    fn create_then_set_in_one_batch_is_valid() {
        let mut w = world();
        apply(&mut w, &[created(1), set(1, &Place {})]).unwrap();
        assert!(w.get::<Place>(EntityId(1)).is_some());
        assert_eq!(w.next_entity_id(), EntityId(2));
    }

    #[test]
    fn refuses_id_reuse_even_after_destroy() {
        let mut w = world();
        apply(&mut w, &[created(1), destroyed(1)]).unwrap();
        assert_eq!(
            refused(&mut w, &[created(1)]),
            (0, ApplyError::IdReused(EntityId(1)))
        );
    }

    #[test]
    fn refuses_set_after_destroy_in_same_batch() {
        let mut w = world();
        let err = refused(&mut w, &[created(1), destroyed(1), set(1, &Place {})]);
        assert_eq!(err, (2, ApplyError::NoSuchEntity(EntityId(1))));
        assert_eq!(w.next_entity_id(), EntityId(1));
    }

    #[test]
    fn refuses_unregistered_component() {
        let mut w = World::empty(ComponentRegistry::new());
        let (_, err) = refused(&mut w, &[created(1), set(1, &Place {})]);
        assert_eq!(err, ApplyError::UnknownComponent("sage.place".into()));
    }

    #[test]
    fn refuses_component_version_mismatch() {
        let mut w = world();
        let mut event = set(1, &Place {});
        if let Event::ComponentSet(s) = &mut event {
            s.component_version = 2;
        }
        let (_, err) = refused(&mut w, &[created(1), event]);
        assert!(matches!(err, ApplyError::ComponentVersion { found: 2, .. }));
    }

    /// `test.counter` v2 renamed `n` to `count`.
    #[derive(bevy_ecs::component::Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
    #[serde(deny_unknown_fields)]
    struct Counter {
        count: u64,
    }

    impl Component for Counter {
        const NAME: &'static str = "test.counter";
        const VERSION: u32 = 2;
    }

    fn counter_v1_to_v2(mut data: Value) -> Result<Value, String> {
        let n = data
            .as_object_mut()
            .and_then(|o| o.remove("n"))
            .ok_or("missing `n`")?;
        Ok(json!({ "count": n }))
    }

    fn set_raw(id: u64, name: &str, version: u32, data: Value) -> Event {
        Event::ComponentSet(ComponentSet {
            id: EntityId(id),
            component: name.into(),
            component_version: version,
            data,
        })
    }

    #[test]
    fn old_component_data_is_upcast_on_apply_and_restore() {
        let registry = || {
            let mut r = ComponentRegistry::with_core();
            r.register::<Counter>();
            r.register_upcaster::<Counter>(1, counter_v1_to_v2);
            r
        };
        let mut w = World::empty(registry());
        apply(
            &mut w,
            &[created(1), set_raw(1, "test.counter", 1, json!({"n": 7}))],
        )
        .unwrap();
        assert_eq!(w.get::<Counter>(EntityId(1)), Some(&Counter { count: 7 }));

        // A snapshot written by the old engine stores version 1 data.
        let mut old = w.snapshot();
        old.entities[0].components.insert(
            "test.counter".into(),
            SnapshotComponent {
                version: 1,
                data: json!({"n": 9}),
            },
        );
        let restored = World::restore(registry(), &old).unwrap();
        assert_eq!(
            restored.get::<Counter>(EntityId(1)),
            Some(&Counter { count: 9 })
        );
        // Snapshots always store the current version.
        assert_eq!(
            restored.snapshot().entities[0].components["test.counter"].version,
            2
        );

        let (_, bad) = refused(&mut w, &[set_raw(1, "test.counter", 1, json!({"m": 1}))]);
        assert!(matches!(bad, ApplyError::ComponentData { .. }), "{bad:?}");
        let (_, newer) = refused(
            &mut w,
            &[set_raw(1, "test.counter", 3, json!({"count": 1}))],
        );
        assert!(matches!(
            newer,
            ApplyError::ComponentVersion { found: 3, .. }
        ));
    }

    #[test]
    fn old_component_data_without_an_upcaster_is_refused() {
        let mut registry = ComponentRegistry::with_core();
        registry.register::<Counter>();
        let mut w = World::empty(registry);
        let (_, err) = refused(
            &mut w,
            &[created(1), set_raw(1, "test.counter", 1, json!({"n": 7}))],
        );
        assert!(matches!(
            err,
            ApplyError::ComponentVersion {
                registered: 2,
                found: 1,
                ..
            }
        ));
    }

    #[test]
    fn refuses_bad_component_data() {
        let mut w = world();
        let event = Event::ComponentSet(ComponentSet {
            id: EntityId(1),
            component: Located::NAME.into(),
            component_version: 1,
            data: json!({"within": "the cupboard"}),
        });
        let (_, err) = refused(&mut w, &[created(1), event]);
        assert!(matches!(err, ApplyError::ComponentData { .. }));
    }

    #[test]
    fn refuses_dangling_reference() {
        let mut w = world();
        let (_, err) = refused(&mut w, &[created(1), set(1, &within(9))]);
        assert_eq!(
            err,
            ApplyError::DanglingReference {
                component: Located::NAME.into(),
                target: EntityId(9)
            }
        );
    }

    #[test]
    fn refuses_destroying_a_referenced_entity_then_allows_it_once_free() {
        let mut w = world();
        let link = Link {
            from: EntityId(1),
            to: EntityId(2),
            label: "out".into(),
        };
        apply(&mut w, &[created(1), created(2), created(3), set(3, &link)]).unwrap();
        let (_, err) = refused(&mut w, &[destroyed(2)]);
        assert_eq!(
            err,
            ApplyError::StillReferenced {
                id: EntityId(2),
                by: EntityId(3),
                component: Link::NAME
            }
        );
        apply(&mut w, &[destroyed(3), destroyed(2)]).unwrap();
        assert!(!w.contains(EntityId(2)));
    }

    #[test]
    fn refuses_containment_cycles() {
        let mut w = world();
        apply(
            &mut w,
            &[
                created(1),
                created(2),
                created(3),
                set(2, &within(1)),
                set(3, &within(2)),
            ],
        )
        .unwrap();
        let (_, self_err) = refused(&mut w, &[set(1, &within(1))]);
        assert!(matches!(self_err, ApplyError::ContainmentCycle { .. }));
        let (_, loop_err) = refused(&mut w, &[set(1, &within(3))]);
        assert_eq!(
            loop_err,
            ApplyError::ContainmentCycle {
                id: EntityId(1),
                within: EntityId(3)
            }
        );
    }

    #[test]
    fn refusal_mid_batch_restores_destroyed_and_changed_entities() {
        let mut w = world();
        let hall = Describable {
            name: "Hall".into(),
            description: "Bare.".into(),
        };
        apply(
            &mut w,
            &[
                created(1),
                set(1, &Place {}),
                set(1, &hall),
                created(2),
                set(2, &within(1)),
            ],
        )
        .unwrap();
        let err = refused(
            &mut w,
            &[
                Event::ComponentRemoved(ComponentRemoved {
                    id: EntityId(2),
                    component: Located::NAME.into(),
                }),
                set(
                    1,
                    &Describable {
                        name: "Changed".into(),
                        description: String::new(),
                    },
                ),
                destroyed(1),
                created(3),
                set(3, &within(99)),
            ],
        );
        assert_eq!(err.0, 4);
        assert_eq!(w.get::<Describable>(EntityId(1)), Some(&hall));
        assert_eq!(w.get::<Located>(EntityId(2)), Some(&within(1)));
        assert!(!w.contains(EntityId(3)));
    }

    #[test]
    fn reads_components_by_name() {
        let mut w = world();
        apply(
            &mut w,
            &[
                created(1),
                set(1, &Place {}),
                created(2),
                set(2, &within(1)),
            ],
        )
        .unwrap();
        assert_eq!(
            w.component_json(EntityId(2), Located::NAME),
            Some(json!({"within": 1}))
        );
        assert_eq!(w.component_json(EntityId(2), Place::NAME), None);
        assert_eq!(w.component_json(EntityId(2), "no.such"), None);
        assert_eq!(w.entities_with(Place::NAME), [EntityId(1)]);
        assert!(w.entities_with("no.such").is_empty());
    }

    #[test]
    fn refuses_tick_going_backwards() {
        let mut w = world();
        w.apply_batch(1, 10, &[created(1)]).unwrap();
        let err = w.apply_batch(2, 9, &[created(2)]).err().unwrap();
        assert_eq!(
            err,
            (
                0,
                ApplyError::TickWentBackwards {
                    tick: 9,
                    current: 10
                }
            )
        );
        assert_eq!((w.last_seq(), w.tick()), (1, 10));
    }

    #[test]
    fn snapshot_restores_to_identical_bytes() {
        let mut w = world();
        let hall = Describable {
            name: "Hall".into(),
            description: "Bare stone.".into(),
        };
        // Entity 1 sits inside entity 3, created later, to prove restore does not depend on
        // containers having lower ids.
        apply(
            &mut w,
            &[
                created(1),
                set(1, &Place {}),
                set(1, &hall),
                created(2),
                set(2, &within(1)),
                created(3),
                set(1, &within(3)),
            ],
        )
        .unwrap();
        let bytes = w.snapshot().to_bytes();
        let restored = World::restore(
            ComponentRegistry::with_core(),
            &Snapshot::from_bytes(&bytes).unwrap(),
        )
        .unwrap();
        assert_eq!(restored.snapshot().to_bytes(), bytes);
        assert_eq!(restored.get::<Describable>(EntityId(1)), Some(&hall));
    }

    #[test]
    fn restore_refuses_snapshot_breaking_a_rule() {
        let mut snapshot = world().snapshot();
        snapshot.next_entity_id = 2;
        let mut components = BTreeMap::new();
        components.insert(
            Located::NAME.to_owned(),
            SnapshotComponent {
                version: 1,
                data: json!({"within": 1}),
            },
        );
        snapshot.entities.push(SnapshotEntity {
            id: EntityId(1),
            components,
        });
        let err = World::restore(ComponentRegistry::with_core(), &snapshot)
            .err()
            .unwrap();
        assert!(matches!(
            err,
            SnapshotError::Content(ApplyError::ContainmentCycle { .. })
        ));
    }

    #[test]
    fn restore_refuses_unknown_snapshot_version() {
        let mut snapshot = world().snapshot();
        snapshot.schema_version = 99;
        assert!(matches!(
            Snapshot::from_bytes(&snapshot.to_bytes()),
            Err(SnapshotError::Version(99))
        ));
    }
}
