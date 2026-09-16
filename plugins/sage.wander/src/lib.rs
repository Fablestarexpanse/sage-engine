//! `sage.wander`: every 20 ticks, moves each located entity along the first link out of its
//! container. Replaces the M1 `harness.wander` test system.

wit_bindgen::generate!({
    path: "../../wit/core",
    world: "plugin",
});

use exports::sage::core::system::Guest;
use sage::core::types::EventRecord;
use sage::core::{entities, space};

const EVERY: u64 = 20;

struct Plugin;

impl Guest for Plugin {
    fn name() -> String {
        "sage.wander".into()
    }

    fn run(tick: u64) -> Result<Vec<EventRecord>, String> {
        if tick % EVERY != 0 {
            return Ok(Vec::new());
        }
        let mut events = Vec::new();
        for id in entities::entities_with("sage.located") {
            let located = entities::get_component(id, "sage.located")
                .ok_or_else(|| format!("entity {id} lost sage.located mid-run"))?;
            let located: serde_json::Value =
                serde_json::from_str(&located).map_err(|e| e.to_string())?;
            let here = located["within"]
                .as_u64()
                .ok_or_else(|| format!("entity {id} has a malformed sage.located"))?;
            if let Some(link) = space::links_from(here).first() {
                events.push(EventRecord {
                    event_type: "ComponentSet".into(),
                    schema_version: 1,
                    payload: serde_json::json!({
                        "id": id,
                        "component": "sage.located",
                        "component_version": 1,
                        "data": {"within": link.to},
                    })
                    .to_string(),
                });
            }
        }
        Ok(events)
    }
}

export!(Plugin);
