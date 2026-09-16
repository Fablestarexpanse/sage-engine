//! Space-graph and containment queries. Results are sorted so callers stay deterministic.

use bevy_ecs::entity::Entity;

use crate::components::{Link, Located};
use crate::world::{EntityId, World};

impl World {
    /// Entities directly inside `container`, by id.
    pub fn contents(&self, container: EntityId) -> Vec<EntityId> {
        self.live_entities()
            .filter(|(_, entity)| self.located_in(*entity) == Some(container))
            .map(|(id, _)| id)
            .collect()
    }

    /// `id`'s containers from the innermost outwards. Empty if `id` is not inside anything.
    pub fn containers(&self, id: EntityId) -> Vec<EntityId> {
        let mut chain = Vec::new();
        let mut current = self.get::<Located>(id).map(|l| l.within);
        while let Some(at) = current {
            chain.push(at);
            current = self.get::<Located>(at).map(|l| l.within);
        }
        chain
    }

    /// Links leaving `place`, as `(link entity, link)`, sorted by label then link id.
    pub fn links_from(&self, place: EntityId) -> Vec<(EntityId, Link)> {
        self.links(|link| link.from == place)
    }

    /// Links arriving at `place`, sorted by label then link id.
    pub fn links_to(&self, place: EntityId) -> Vec<(EntityId, Link)> {
        self.links(|link| link.to == place)
    }

    /// The link leaving `place` with exactly `label`. If several share a label, the lowest id
    /// wins, so the answer never depends on storage order.
    pub fn link_named(&self, place: EntityId, label: &str) -> Option<(EntityId, Link)> {
        self.links_from(place)
            .into_iter()
            .find(|(_, link)| link.label == label)
    }

    fn links(&self, keep: impl Fn(&Link) -> bool) -> Vec<(EntityId, Link)> {
        let mut found: Vec<(EntityId, Link)> = self
            .live_entities()
            .filter_map(|(id, entity)| {
                self.ecs
                    .get::<Link>(entity)
                    .filter(|link| keep(link))
                    .map(|link| (id, link.clone()))
            })
            .collect();
        found.sort_by(|(a_id, a), (b_id, b)| a.label.cmp(&b.label).then(a_id.cmp(b_id)));
        found
    }

    fn located_in(&self, entity: Entity) -> Option<EntityId> {
        self.ecs.get::<Located>(entity).map(|l| l.within)
    }
}

#[cfg(test)]
mod tests {
    use crate::journal::test_log::MemoryLog;
    use crate::{
        Component, ComponentRegistry, ComponentSet, EntityCreated, EntityId, Event, Journal, Link,
        Located, Place, Upcasters,
    };

    fn set<C: Component>(id: u64, c: &C) -> Event {
        Event::ComponentSet(ComponentSet {
            id: EntityId(id),
            component: C::NAME.into(),
            component_version: C::VERSION,
            data: serde_json::to_value(c).unwrap(),
        })
    }

    fn created(id: u64) -> Event {
        Event::EntityCreated(EntityCreated { id: EntityId(id) })
    }

    fn link(from: u64, to: u64, label: &str) -> Link {
        Link {
            from: EntityId(from),
            to: EntityId(to),
            label: label.into(),
        }
    }

    /// Places 1 and 2; links 3 (1 -> 2 "north"), 4 (2 -> 1 "south"), 5 (1 -> 2 "gate");
    /// entity 6 inside 1, entity 7 inside 6.
    fn journal() -> Journal<MemoryLog> {
        let mut j = Journal::open(
            MemoryLog::default(),
            ComponentRegistry::with_core(),
            Upcasters::core(),
        )
        .unwrap();
        let mut events: Vec<Event> = (1..=7).map(created).collect();
        events.extend([
            set(1, &Place {}),
            set(2, &Place {}),
            set(3, &link(1, 2, "north")),
            set(4, &link(2, 1, "south")),
            set(5, &link(1, 2, "gate")),
            set(
                6,
                &Located {
                    within: EntityId(1),
                },
            ),
            set(
                7,
                &Located {
                    within: EntityId(6),
                },
            ),
        ]);
        j.commit(0, &events).unwrap();
        j
    }

    #[test]
    fn links_are_directed_and_sorted_by_label() {
        let j = journal();
        let from_1: Vec<_> = j
            .world()
            .links_from(EntityId(1))
            .into_iter()
            .map(|(id, l)| (id.0, l.label))
            .collect();
        assert_eq!(from_1, [(5, "gate".into()), (3, "north".into())]);
        assert_eq!(j.world().links_to(EntityId(1)).len(), 1);
        assert_eq!(
            j.world().link_named(EntityId(2), "south").map(|(id, _)| id),
            Some(EntityId(4))
        );
        assert!(j.world().link_named(EntityId(2), "north").is_none());
    }

    #[test]
    fn contents_and_containers() {
        let j = journal();
        assert_eq!(j.world().contents(EntityId(1)), [EntityId(6)]);
        assert_eq!(
            j.world().containers(EntityId(7)),
            [EntityId(6), EntityId(1)]
        );
        assert!(j.world().containers(EntityId(1)).is_empty());
    }

    #[test]
    fn moving_updates_contents() {
        let mut j = journal();
        j.commit(
            1,
            &[set(
                6,
                &Located {
                    within: EntityId(2),
                },
            )],
        )
        .unwrap();
        assert!(j.world().contents(EntityId(1)).is_empty());
        assert_eq!(j.world().contents(EntityId(2)), [EntityId(6)]);
        assert_eq!(
            j.world().containers(EntityId(7)),
            [EntityId(6), EntityId(2)]
        );
    }
}
