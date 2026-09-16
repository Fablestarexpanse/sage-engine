//! The world: a projection of the event log onto a `bevy_ecs` world.

use std::collections::{BTreeMap, BTreeSet};

use bevy_ecs::entity::Entity;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

use crate::component::ComponentRegistry;
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

/// Why an event cannot be applied. Checked before anything is written.
#[derive(Debug, Error, PartialEq)]
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
    /// The snapshot's contents fail the same checks events do.
    #[error("snapshot content is invalid: {0}")]
    Content(#[from] ApplyError),
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

/// Current world state. Read it freely; change it only through [`crate::Journal`].
pub struct World {
    ecs: bevy_ecs::world::World,
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

    /// Checks that `events`, applied in order, would all succeed. Changes nothing.
    pub(crate) fn check_batch(&self, events: &[Event]) -> Result<(), (usize, ApplyError)> {
        let mut created = BTreeSet::new();
        let mut destroyed = BTreeSet::new();
        let mut next_id = self.next_entity_id;
        let live = |id: &EntityId, created: &BTreeSet<EntityId>, destroyed: &BTreeSet<EntityId>| {
            (self.index.contains_key(id) || created.contains(id)) && !destroyed.contains(id)
        };

        for (i, event) in events.iter().enumerate() {
            let fail = |e| (i, e);
            match event {
                Event::EntityCreated(EntityCreated { id }) => {
                    if id.0 < next_id {
                        return Err(fail(ApplyError::IdReused(*id)));
                    }
                    next_id = id.0 + 1;
                    created.insert(*id);
                }
                Event::EntityDestroyed(EntityDestroyed { id }) => {
                    if !live(id, &created, &destroyed) {
                        return Err(fail(ApplyError::NoSuchEntity(*id)));
                    }
                    destroyed.insert(*id);
                }
                Event::ComponentSet(set) => {
                    if !live(&set.id, &created, &destroyed) {
                        return Err(fail(ApplyError::NoSuchEntity(set.id)));
                    }
                    self.check_component(set).map_err(fail)?;
                }
                Event::ComponentRemoved(ComponentRemoved { id, component }) => {
                    if !live(id, &created, &destroyed) {
                        return Err(fail(ApplyError::NoSuchEntity(*id)));
                    }
                    if self.registry.get(component).is_none() {
                        return Err(fail(ApplyError::UnknownComponent(component.clone())));
                    }
                }
            }
        }
        Ok(())
    }

    fn check_component(&self, set: &ComponentSet) -> Result<(), ApplyError> {
        let entry = self
            .registry
            .get(&set.component)
            .ok_or_else(|| ApplyError::UnknownComponent(set.component.clone()))?;
        if entry.version != set.component_version {
            return Err(ApplyError::ComponentVersion {
                component: set.component.clone(),
                registered: entry.version,
                found: set.component_version,
            });
        }
        (entry.check)(set.data.clone()).map_err(|e| ApplyError::ComponentData {
            component: set.component.clone(),
            reason: e.to_string(),
        })
    }

    /// Applies one event that already passed [`World::check_batch`]. Panics on a failed
    /// precondition, since that means the check and apply paths disagree.
    pub(crate) fn apply_checked(&mut self, seq: u64, tick: u64, event: &Event) {
        assert_eq!(seq, self.last_seq + 1, "events must be applied in sequence");
        match event {
            Event::EntityCreated(EntityCreated { id }) => {
                let entity = self.ecs.spawn(*id).id();
                self.index.insert(*id, entity);
                self.next_entity_id = id.0 + 1;
            }
            Event::EntityDestroyed(EntityDestroyed { id }) => {
                let entity = self.index.remove(id).expect("checked: entity exists");
                self.ecs.despawn(entity);
            }
            Event::ComponentSet(set) => {
                let entry = self
                    .registry
                    .get(&set.component)
                    .expect("checked: registered");
                let entity = self.index[&set.id];
                (entry.insert)(&mut self.ecs.entity_mut(entity), set.data.clone())
                    .expect("checked: data deserializes");
            }
            Event::ComponentRemoved(ComponentRemoved { id, component }) => {
                let entry = self.registry.get(component).expect("checked: registered");
                let entity = self.index[id];
                (entry.remove)(&mut self.ecs.entity_mut(entity));
            }
        }
        self.last_seq = seq;
        self.tick = tick;
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

    /// Rebuilds a world from a snapshot, validating every component like an event.
    pub(crate) fn restore(
        registry: ComponentRegistry,
        snapshot: &Snapshot,
    ) -> Result<World, SnapshotError> {
        if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION {
            return Err(SnapshotError::Version(snapshot.schema_version));
        }
        let mut world = World::empty(registry);
        for e in &snapshot.entities {
            if e.id.0 >= snapshot.next_entity_id || world.index.contains_key(&e.id) {
                return Err(ApplyError::IdReused(e.id).into());
            }
            for (name, component) in &e.components {
                world.check_component(&ComponentSet {
                    id: e.id,
                    component: name.clone(),
                    component_version: component.version,
                    data: component.data.clone(),
                })?;
            }
            let entity = world.ecs.spawn(e.id).id();
            world.index.insert(e.id, entity);
            for (name, component) in &e.components {
                let entry = world.registry.get(name).expect("checked: registered");
                (entry.insert)(&mut world.ecs.entity_mut(entity), component.data.clone())
                    .expect("checked: data deserializes");
            }
        }
        world.next_entity_id = snapshot.next_entity_id;
        world.last_seq = snapshot.last_seq;
        world.tick = snapshot.tick;
        Ok(world)
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::{Component, Describable, Located, Place};

    fn created(id: u64) -> Event {
        Event::EntityCreated(EntityCreated { id: EntityId(id) })
    }

    fn set<C: Component>(id: u64, c: &C) -> Event {
        Event::ComponentSet(ComponentSet {
            id: EntityId(id),
            component: C::NAME.into(),
            component_version: C::VERSION,
            data: serde_json::to_value(c).unwrap(),
        })
    }

    fn apply_all(world: &mut World, events: &[Event]) {
        world.check_batch(events).unwrap();
        for event in events {
            let seq = world.last_seq() + 1;
            world.apply_checked(seq, 0, event);
        }
    }

    #[test]
    fn create_then_set_in_one_batch_is_valid() {
        let mut world = World::empty(ComponentRegistry::with_core());
        apply_all(&mut world, &[created(1), set(1, &Place {})]);
        assert!(world.get::<Place>(EntityId(1)).is_some());
        assert_eq!(world.next_entity_id(), EntityId(2));
    }

    #[test]
    fn refuses_id_reuse_even_after_destroy() {
        let mut world = World::empty(ComponentRegistry::with_core());
        apply_all(
            &mut world,
            &[
                created(1),
                Event::EntityDestroyed(EntityDestroyed { id: EntityId(1) }),
            ],
        );
        let (i, err) = world.check_batch(&[created(1)]).unwrap_err();
        assert_eq!((i, err), (0, ApplyError::IdReused(EntityId(1))));
    }

    #[test]
    fn refuses_set_after_destroy_in_same_batch() {
        let world = World::empty(ComponentRegistry::with_core());
        let batch = [
            created(1),
            Event::EntityDestroyed(EntityDestroyed { id: EntityId(1) }),
            set(1, &Place {}),
        ];
        let (i, err) = world.check_batch(&batch).unwrap_err();
        assert_eq!((i, err), (2, ApplyError::NoSuchEntity(EntityId(1))));
    }

    #[test]
    fn refuses_unregistered_component() {
        let world = World::empty(ComponentRegistry::new());
        let (_, err) = world
            .check_batch(&[created(1), set(1, &Place {})])
            .unwrap_err();
        assert_eq!(err, ApplyError::UnknownComponent("sage.place".into()));
    }

    #[test]
    fn refuses_component_version_mismatch() {
        let world = World::empty(ComponentRegistry::with_core());
        let mut event = set(1, &Place {});
        if let Event::ComponentSet(s) = &mut event {
            s.component_version = 2;
        }
        let (_, err) = world.check_batch(&[created(1), event]).unwrap_err();
        assert!(matches!(err, ApplyError::ComponentVersion { found: 2, .. }));
    }

    #[test]
    fn refuses_bad_component_data() {
        let world = World::empty(ComponentRegistry::with_core());
        let event = Event::ComponentSet(ComponentSet {
            id: EntityId(1),
            component: Located::NAME.into(),
            component_version: 1,
            data: json!({"within": "the cupboard"}),
        });
        let (_, err) = world.check_batch(&[created(1), event]).unwrap_err();
        assert!(matches!(err, ApplyError::ComponentData { .. }));
    }

    #[test]
    fn snapshot_restores_to_identical_bytes() {
        let mut world = World::empty(ComponentRegistry::with_core());
        let hall = Describable {
            name: "Hall".into(),
            description: "Bare stone.".into(),
        };
        apply_all(
            &mut world,
            &[
                created(1),
                set(1, &Place {}),
                set(1, &hall),
                created(2),
                set(
                    2,
                    &Located {
                        within: EntityId(1),
                    },
                ),
            ],
        );
        let bytes = world.snapshot().to_bytes();
        let restored = World::restore(
            ComponentRegistry::with_core(),
            &Snapshot::from_bytes(&bytes).unwrap(),
        )
        .unwrap();
        assert_eq!(restored.snapshot().to_bytes(), bytes);
        assert_eq!(restored.get::<Describable>(EntityId(1)), Some(&hall));
    }

    #[test]
    fn restore_refuses_unknown_snapshot_version() {
        let mut snapshot = World::empty(ComponentRegistry::with_core()).snapshot();
        snapshot.schema_version = 99;
        assert!(matches!(
            Snapshot::from_bytes(&snapshot.to_bytes()),
            Err(SnapshotError::Version(99))
        ));
    }
}
