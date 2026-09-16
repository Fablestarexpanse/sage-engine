//! Tries to put words in someone's mouth: proposes a core `sage.said` occurrence. The host
//! must refuse it, because a plugin may only emit occurrence kinds under its own name.

wit_bindgen::generate!({
    path: "../../../../wit/core",
    world: "plugin",
});

use exports::sage::core::system::Guest;
use sage::core::types::EventRecord;

struct Plugin;

impl Guest for Plugin {
    fn name() -> String {
        "fixture.impostor".into()
    }

    fn run(_tick: u64) -> Result<Vec<EventRecord>, String> {
        Ok(vec![EventRecord {
            event_type: "Occurred".into(),
            schema_version: 1,
            payload: r#"{"kind":"sage.said","kind_version":1,"actor":null,"places":[],"targets":[],"data":{"text":"I confess"}}"#.into(),
        }])
    }
}

export!(Plugin);
