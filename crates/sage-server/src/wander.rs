//! M1 test harness only: gives a world steady, deterministic activity so the run loop, restart
//! and 24-hour gates have something to exercise. Behaviour belongs in code fragments; this goes
//! away when M2 can load a plugin that does the same.

use std::sync::Arc;

use sage_core::{Component, ComponentSet, Event, Located, System, World};

/// Every `every` ticks, moves each located entity along the first link out of where it is.
pub struct Wander {
    pub every: u64,
}

impl System for Wander {
    fn name(&self) -> &'static str {
        "harness.wander"
    }

    fn run(&mut self, world: &Arc<World>, tick: u64) -> Result<Vec<Event>, String> {
        if !tick.is_multiple_of(self.every) {
            return Ok(Vec::new());
        }
        Ok((1..world.next_entity_id().0)
            .map(sage_core::EntityId)
            .filter_map(|id| {
                let here = world.get::<Located>(id)?.within;
                let (_, link) = world.links_from(here).into_iter().next()?;
                Some(Event::ComponentSet(ComponentSet {
                    id,
                    component: Located::NAME.into(),
                    component_version: Located::VERSION,
                    data: serde_json::to_value(Located { within: link.to })
                        .expect("Located serializes"),
                }))
            })
            .collect())
    }
}
