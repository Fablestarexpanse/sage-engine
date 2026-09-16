//! Never returns from `run`. Proves fuel stops a runaway plugin.

wit_bindgen::generate!({
    path: "../../../../wit/core",
    world: "plugin",
});

use exports::sage::core::system::Guest;
use sage::core::types::EventRecord;

struct Plugin;

impl Guest for Plugin {
    fn name() -> String {
        "fixture.spinner".into()
    }

    fn run(tick: u64) -> Result<Vec<EventRecord>, String> {
        let mut n = tick;
        loop {
            n = std::hint::black_box(n.wrapping_mul(31).wrapping_add(7));
        }
    }
}

export!(Plugin);
