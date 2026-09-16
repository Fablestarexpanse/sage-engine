//! Tries to allocate far more memory than any plugin is allowed. Proves the memory cap holds.

wit_bindgen::generate!({
    path: "../../../../wit/core",
    world: "plugin",
});

use exports::sage::core::system::Guest;
use sage::core::types::EventRecord;

struct Plugin;

impl Guest for Plugin {
    fn name() -> String {
        "fixture.hog".into()
    }

    fn run(_tick: u64) -> Result<Vec<EventRecord>, String> {
        let mut hoard: Vec<Vec<u8>> = Vec::new();
        loop {
            hoard.push(std::hint::black_box(vec![1u8; 8 * 1024 * 1024]));
        }
    }
}

export!(Plugin);
