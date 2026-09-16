//! Upcasters turn stored event payloads written at an old schema version into the current
//! shape on read. The log itself is never rewritten.

use std::collections::BTreeMap;

use serde_json::Value;
use thiserror::Error;

/// Converts a payload from version `n` to version `n + 1`.
pub type UpcastFn = fn(Value) -> Result<Value, String>;

/// Why a stored payload could not be brought to the current version.
#[derive(Debug, Error, PartialEq)]
pub enum UpcastError {
    /// The payload is newer than this engine understands.
    #[error(
        "`{event_type}` v{found} was written by a newer engine (this engine reads up to v{current})"
    )]
    FromNewerEngine {
        /// Event type.
        event_type: String,
        /// Version found in the log.
        found: u32,
        /// Newest version this engine knows.
        current: u32,
    },
    /// No upcaster is registered for one step of the chain.
    #[error("no upcaster for `{event_type}` v{from} -> v{}", from + 1)]
    Missing {
        /// Event type.
        event_type: String,
        /// Version that has no upcaster.
        from: u32,
    },
    /// An upcaster rejected the payload.
    #[error("upcaster for `{event_type}` v{from} failed: {reason}")]
    Failed {
        /// Event type.
        event_type: String,
        /// Version the failing upcaster starts from.
        from: u32,
        /// Upcaster's message.
        reason: String,
    },
}

/// Registered upcasters, keyed by event type and the version they convert from.
#[derive(Default)]
pub struct Upcasters {
    steps: BTreeMap<(String, u32), UpcastFn>,
}

impl Upcasters {
    /// No upcasters. Correct while every event type is still at version 1.
    pub fn new() -> Self {
        Self::default()
    }

    /// Registers the step `from` -> `from + 1` for `event_type`.
    pub fn register(&mut self, event_type: &str, from: u32, step: UpcastFn) {
        self.steps.insert((event_type.to_owned(), from), step);
    }

    /// Brings `payload` from version `found` to `current`, one step at a time.
    pub fn upcast(
        &self,
        event_type: &str,
        found: u32,
        current: u32,
        mut payload: Value,
    ) -> Result<Value, UpcastError> {
        if found > current {
            return Err(UpcastError::FromNewerEngine {
                event_type: event_type.to_owned(),
                found,
                current,
            });
        }
        for from in found..current {
            let step = self
                .steps
                .get(&(event_type.to_owned(), from))
                .ok_or_else(|| UpcastError::Missing {
                    event_type: event_type.to_owned(),
                    from,
                })?;
            payload = step(payload).map_err(|reason| UpcastError::Failed {
                event_type: event_type.to_owned(),
                from,
                reason,
            })?;
        }
        Ok(payload)
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn rename_who_to_actor(mut v: Value) -> Result<Value, String> {
        let who = v
            .as_object_mut()
            .and_then(|o| o.remove("who"))
            .ok_or("missing `who`")?;
        v["actor"] = who;
        Ok(v)
    }

    fn add_volume(mut v: Value) -> Result<Value, String> {
        v["volume"] = json!("normal");
        Ok(v)
    }

    fn upcasters() -> Upcasters {
        let mut u = Upcasters::new();
        u.register("Spoke", 1, rename_who_to_actor);
        u.register("Spoke", 2, add_volume);
        u
    }

    #[test]
    fn chains_steps_from_old_version_to_current() {
        let old = json!({"who": 7, "text": "hello"});
        let now = upcasters().upcast("Spoke", 1, 3, old).unwrap();
        assert_eq!(
            now,
            json!({"actor": 7, "text": "hello", "volume": "normal"})
        );
    }

    #[test]
    fn current_version_passes_through_unchanged() {
        let v = json!({"actor": 7});
        assert_eq!(upcasters().upcast("Spoke", 3, 3, v.clone()).unwrap(), v);
    }

    #[test]
    fn refuses_payload_from_newer_engine() {
        let err = upcasters().upcast("Spoke", 4, 3, json!({})).unwrap_err();
        assert!(matches!(err, UpcastError::FromNewerEngine { found: 4, .. }));
    }

    #[test]
    fn refuses_gap_in_chain() {
        let err = Upcasters::new()
            .upcast("Spoke", 1, 2, json!({}))
            .unwrap_err();
        assert!(matches!(err, UpcastError::Missing { from: 1, .. }));
    }

    #[test]
    fn surfaces_upcaster_failure() {
        let err = upcasters().upcast("Spoke", 1, 3, json!({})).unwrap_err();
        assert!(matches!(err, UpcastError::Failed { from: 1, .. }));
    }
}
