//! `sage.dialogue`: directed conversation. `tell <name> <text>` reaches the teller and the
//! named actor, if that actor is in the same place. `<name>` is the actor's full name when it
//! is one word, or the first word of it ("Tamsin" for "Tamsin Reed") when only one actor here
//! answers to that.

wit_bindgen::generate!({
    path: "../../wit/core",
    world: "command-plugin",
});

use exports::sage::core::commands::{self, Line, Outcome};
use exports::sage::core::system;
use sage::core::types::EventRecord;
use sage::core::{entities, space};

const ID: &str = "sage.dialogue";

struct Plugin;

impl system::Guest for Plugin {
    fn name() -> String {
        ID.into()
    }

    fn run(_tick: u64) -> Result<Vec<EventRecord>, String> {
        Ok(Vec::new())
    }
}

fn line(key: &str, params: &[(&str, &str)]) -> Line {
    Line {
        key: format!("{ID}.{key}"),
        params: params
            .iter()
            .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
            .collect(),
    }
}

fn say_only(line: Line) -> Outcome {
    Outcome {
        events: Vec::new(),
        output: vec![line],
    }
}

fn name_of(id: u64) -> Option<String> {
    let describable = entities::get_component(id, "sage.describable")?;
    let value: serde_json::Value = serde_json::from_str(&describable).ok()?;
    value["name"].as_str().map(str::to_owned)
}

impl commands::Guest for Plugin {
    fn verbs() -> Vec<String> {
        vec!["tell".into()]
    }

    fn lexicon() -> Vec<(String, String)> {
        [
            ("told.self", "You tell {target}, \"{text}\""),
            ("told.target", "{actor} tells you, \"{text}\""),
            ("tell.usage", "Tell whom what?"),
            ("tell.nobody", "Nobody here answers to \"{name}\"."),
            ("tell.ambiguous", "More than one here answers to \"{name}\"."),
        ]
        .iter()
        .map(|(key, template)| (format!("{ID}.{key}"), (*template).to_owned()))
        .collect()
    }

    fn handle(actor: u64, verb: String, args: String, _tick: u64) -> Result<Outcome, String> {
        if verb != "tell" {
            return Err(format!("{ID} does not handle `{verb}`"));
        }
        let Some((name, text)) = args.trim().split_once(char::is_whitespace) else {
            return Ok(say_only(line("tell.usage", &[])));
        };
        let text = text.trim();
        let here = entities::get_component(actor, "sage.located")
            .and_then(|json| serde_json::from_str::<serde_json::Value>(&json).ok())
            .and_then(|value| value["within"].as_u64());
        let others: Vec<(u64, String)> = here
            .map(|place| {
                space::contents(place)
                    .into_iter()
                    .filter(|id| *id != actor && entities::get_component(*id, "sage.actor").is_some())
                    .filter_map(|id| name_of(id).map(|n| (id, n)))
                    .collect()
            })
            .unwrap_or_default();
        let exact: Vec<u64> = others
            .iter()
            .filter(|(_, n)| n.eq_ignore_ascii_case(name))
            .map(|(id, _)| *id)
            .collect();
        let by_first_word: Vec<u64> = others
            .iter()
            .filter(|(_, n)| {
                n.split_whitespace()
                    .next()
                    .is_some_and(|first| first.eq_ignore_ascii_case(name))
            })
            .map(|(id, _)| *id)
            .collect();
        let target = match (exact.as_slice(), by_first_word.as_slice()) {
            ([id], _) => *id,
            ([], [id]) => *id,
            ([], []) => return Ok(say_only(line("tell.nobody", &[("name", name)]))),
            _ => return Ok(say_only(line("tell.ambiguous", &[("name", name)]))),
        };
        let occurred = serde_json::json!({
            "kind": format!("{ID}.told"),
            "kind_version": 1,
            "actor": actor,
            "places": [],
            "targets": [target],
            "data": { "text": text },
        });
        Ok(Outcome {
            events: vec![EventRecord {
                event_type: "Occurred".into(),
                schema_version: 1,
                payload: occurred.to_string(),
            }],
            output: Vec::new(),
        })
    }
}

export!(Plugin);
