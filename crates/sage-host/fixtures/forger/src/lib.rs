//! Proposes bad events. Tick 1: a valid event the world refuses (reuses entity id 1). Tick 2:
//! an event type that does not exist, which suspends the plugin.

wit_bindgen::generate!({
    path: "../../../../wit/core",
    world: "plugin",
});

use exports::sage::core::system::Guest;
use sage::core::types::EventRecord;

struct Plugin;

impl Guest for Plugin {
    fn name() -> String {
        "fixture.forger".into()
    }

    fn run(tick: u64) -> Result<Vec<EventRecord>, String> {
        let record = match tick {
            1 => EventRecord {
                event_type: "EntityCreated".into(),
                schema_version: 1,
                payload: r#"{"id":1}"#.into(),
            },
            2 => EventRecord {
                event_type: "EverythingDeleted".into(),
                schema_version: 1,
                payload: "{}".into(),
            },
            _ => return Ok(Vec::new()),
        };
        Ok(vec![record])
    }
}

export!(Plugin);
