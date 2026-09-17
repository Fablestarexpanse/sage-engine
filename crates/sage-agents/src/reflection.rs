//! Reflection: now and then a model-driven agent stops to draw conclusions from what it has
//! perceived. Reflections are ordinary occurrences in the log (`sage.mind.reflected`, perceived
//! only by the agent), so they enter memory and retrieval and survive restarts like anything
//! else.
//!
//! When to reflect is decided from memory alone: once the importance of everything perceived
//! since the last reflection adds up to the mind's threshold. Nothing reflects without a model.

use std::sync::{Arc, Mutex};

use sage_core::{Actor, EntityId, Event, Occurred, System, World};
use serde_json::{Value, json};

use crate::memory::Memory;
use crate::mind::Mind;
use crate::retrieval::importance;

/// The occurrence kind of a reflection.
pub const REFLECTED: &str = "sage.mind.reflected";

/// The threshold for model-driven minds that do not set `reflect_threshold`.
pub const DEFAULT_REFLECT_THRESHOLD: f64 = 50.0;

/// Ticks to wait after a failed reflection before trying again.
pub const REFLECTION_BACKOFF: u64 = 100;

/// Most reflections accepted from one answer.
pub const MAX_REFLECTIONS: usize = 3;

/// Longest reflection accepted.
pub const MAX_REFLECTION_CHARS: usize = 200;

/// The occurrence kind of a memory an agent was placed with (from a card's lorebook).
pub const REMEMBERED: &str = "sage.mind.remembered";

/// Default wording for reflections and placed memories, in English.
pub const LEXICON_ENGLISH: [(&str, &str); 2] = [
    ("sage.mind.reflected.self", "You think: {text}"),
    ("sage.mind.remembered.self", "You remember: {text}"),
];

/// The memories since `agent`'s last reflection, and the sum of their importance. Earlier
/// reflections are not counted, and neither are memories the agent was placed with: those are
/// what it already knew, not new experience to reflect on.
pub fn since_last_reflection<'a>(
    world: &World,
    agent: EntityId,
    mind: &Mind,
    memories: &[&'a Memory],
) -> (Vec<&'a Memory>, f64) {
    let start = memories
        .iter()
        .rposition(|m| m.occurred.kind == REFLECTED && m.occurred.actor == Some(agent))
        .map_or(0, |i| i + 1);
    let since: Vec<&Memory> = memories[start..]
        .iter()
        .filter(|m| m.occurred.kind != REMEMBERED)
        .copied()
        .collect();
    let total = since
        .iter()
        .map(|m| importance(world, agent, mind, &m.occurred))
        .sum();
    (since, total)
}

/// Checks a reflection reply: exactly `{"reflections": [...]}` with 1 to
/// [`MAX_REFLECTIONS`] non-empty lines of at most [`MAX_REFLECTION_CHARS`] characters.
pub fn check_reflections(reply: &str) -> Result<Vec<String>, String> {
    let value: Value = serde_json::from_str(reply.trim())
        .map_err(|_| "reply is not the JSON object asked for".to_owned())?;
    let fields = value.as_object().ok_or("reply is not a JSON object")?;
    if fields.len() != 1 {
        return Err("reply must have exactly one field, `reflections`".into());
    }
    let items = fields
        .get("reflections")
        .and_then(Value::as_array)
        .ok_or("reply has no `reflections` list")?;
    if items.is_empty() || items.len() > MAX_REFLECTIONS {
        return Err(format!(
            "expected 1 to {MAX_REFLECTIONS} reflections, got {}",
            items.len()
        ));
    }
    items
        .iter()
        .map(|item| {
            let text = item.as_str().ok_or("a reflection is not a string")?.trim();
            if text.is_empty() {
                return Err("a reflection is empty".to_owned());
            }
            if text.chars().count() > MAX_REFLECTION_CHARS {
                return Err(format!(
                    "a reflection is longer than {MAX_REFLECTION_CHARS} characters"
                ));
            }
            if text.chars().any(char::is_control) {
                return Err("a reflection contains control characters".into());
            }
            Ok(text.to_owned())
        })
        .collect()
}

/// The JSON schema a reflection reply must follow, as an OpenAI `response_format`.
pub fn reflection_format() -> Value {
    json!({
        "type": "json_schema",
        "json_schema": {
            "name": "reflections",
            "strict": true,
            "schema": {
                "type": "object",
                "properties": {
                    "reflections": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_REFLECTIONS,
                        "items": {"type": "string", "maxLength": MAX_REFLECTION_CHARS}
                    }
                },
                "required": ["reflections"],
                "additionalProperties": false
            }
        }
    })
}

/// A scheduler system that commits reflections handed to it, inside the next tick, so they
/// are logged like any other occurrence. Clone it to keep a handle for pushing.
#[derive(Clone, Default)]
pub struct Reflections {
    queue: Arc<Mutex<Vec<(EntityId, String)>>>,
}

impl Reflections {
    /// An empty queue.
    pub fn new() -> Reflections {
        Reflections::default()
    }

    /// Queues a reflection for `agent`, committed on the next step.
    pub fn push(&self, agent: EntityId, text: String) {
        self.queue
            .lock()
            .expect("reflection queue")
            .push((agent, text));
    }
}

impl System for Reflections {
    fn name(&self) -> &'static str {
        "sage.agents.reflections"
    }

    fn run(&mut self, world: &Arc<World>, _tick: u64) -> Result<Vec<Event>, String> {
        let queued = std::mem::take(&mut *self.queue.lock().expect("reflection queue"));
        Ok(queued
            .into_iter()
            .filter(|(agent, _)| world.get::<Actor>(*agent).is_some())
            .map(|(agent, text)| {
                Event::Occurred(Occurred {
                    kind: REFLECTED.into(),
                    kind_version: 1,
                    actor: Some(agent),
                    places: Vec::new(),
                    targets: Vec::new(),
                    data: json!({ "text": text }),
                    audience: Vec::new(),
                })
            })
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_one_to_three_short_reflections() {
        assert_eq!(
            check_reflections(
                r#"{"reflections": [" Bo is hiding something. ", "The gate matters."]}"#
            ),
            Ok(vec![
                "Bo is hiding something.".into(),
                "The gate matters.".into()
            ])
        );
    }

    #[test]
    fn refuses_anything_else() {
        let long = format!(
            r#"{{"reflections": ["{}"]}}"#,
            "a".repeat(MAX_REFLECTION_CHARS + 1)
        );
        for (reply, why) in [
            ("I think Bo lies.", "not the JSON object"),
            (r#"{"reflections": []}"#, "1 to 3"),
            (r#"{"reflections": ["a", "b", "c", "d"]}"#, "1 to 3"),
            (
                r#"{"reflections": ["ok"], "command": "say hi"}"#,
                "exactly one field",
            ),
            (r#"{"reflections": "Bo lies"}"#, "no `reflections` list"),
            (r#"{"reflections": [7]}"#, "not a string"),
            (r#"{"reflections": ["  "]}"#, "empty"),
            (long.as_str(), "longer than"),
        ] {
            let err = check_reflections(reply).unwrap_err();
            assert!(err.contains(why), "{reply} -> {err}");
        }
    }
}
