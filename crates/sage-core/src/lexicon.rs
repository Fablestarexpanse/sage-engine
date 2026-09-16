//! Player-facing text. The engine never builds sentences: it emits [`Line`]s (a key plus named
//! parameters) and a [`Lexicon`] renders them. Every template can be overridden per world.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// Something to show a player, before wording is chosen.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct Line {
    /// Template key, e.g. `sage.go.no-way`.
    pub key: String,
    /// Values for `{name}` placeholders.
    pub params: BTreeMap<String, String>,
}

impl Line {
    /// A line with no parameters.
    pub fn new(key: impl Into<String>) -> Line {
        Line {
            key: key.into(),
            params: BTreeMap::new(),
        }
    }

    /// Adds a parameter.
    pub fn with(mut self, name: impl Into<String>, value: impl Into<String>) -> Line {
        self.params.insert(name.into(), value.into());
        self
    }
}

/// Templates by key.
#[derive(Clone, Debug, Default)]
pub struct Lexicon {
    templates: BTreeMap<String, String>,
}

/// Key used for a name placeholder that has no value (an entity with no name).
pub const UNKNOWN_NAME: &str = "sage.name.unknown";

const CORE_ENGLISH: &[(&str, &str)] = &[
    (UNKNOWN_NAME, "someone"),
    ("sage.look.place", "{name}\n{description}"),
    ("sage.look.exits", "Ways on: {exits}."),
    ("sage.look.no-exits", "There is no way on."),
    ("sage.look.contents", "Here: {things}."),
    ("sage.look.nowhere", "You are nowhere."),
    ("sage.go.where", "Go where?"),
    ("sage.go.no-way", "There is no way {label} from here."),
    ("sage.say.what", "Say what?"),
    ("sage.emote.what", "Emote what?"),
    (
        "sage.command.unknown",
        "Nothing here understands \"{verb}\".",
    ),
    ("sage.command.failed", "That did not work."),
    ("sage.said.self", "You say, \"{text}\""),
    ("sage.said.other", "{actor} says, \"{text}\""),
    ("sage.emoted.self", "{actor} {text}"),
    ("sage.emoted.other", "{actor} {text}"),
    ("sage.travelled.self", "You go {label}."),
    ("sage.travelled.other.0", "{actor} leaves {label}."),
    ("sage.travelled.other.1", "{actor} arrives."),
];

impl Lexicon {
    /// An empty lexicon.
    pub fn new() -> Lexicon {
        Lexicon::default()
    }

    /// The engine's default English templates.
    pub fn core_english() -> Lexicon {
        let mut lexicon = Lexicon::new();
        for (key, template) in CORE_ENGLISH {
            lexicon.set(*key, *template);
        }
        lexicon
    }

    /// Sets or replaces a template.
    pub fn set(&mut self, key: impl Into<String>, template: impl Into<String>) {
        self.templates.insert(key.into(), template.into());
    }

    /// The template for `key`. A key ending in `.other.<n>` falls back to `.other`.
    pub fn template(&self, key: &str) -> Option<&str> {
        if let Some(template) = self.templates.get(key) {
            return Some(template);
        }
        let (base, last) = key.rsplit_once('.')?;
        if base.ends_with(".other") && last.bytes().all(|b| b.is_ascii_digit()) {
            return self.templates.get(base).map(String::as_str);
        }
        None
    }

    /// Renders a line, or `None` if no template exists (the line is not meant to be shown in
    /// this world). A placeholder with no value renders as [`UNKNOWN_NAME`], or stays literal
    /// if that template is missing too.
    pub fn render(&self, line: &Line) -> Option<String> {
        let template = self.template(&line.key)?;
        let mut out = String::with_capacity(template.len());
        let mut rest = template;
        while let Some(open) = rest.find('{') {
            out.push_str(&rest[..open]);
            let after = &rest[open + 1..];
            match after.find('}') {
                Some(close) => {
                    let name = &after[..close];
                    match line.params.get(name) {
                        Some(value) => out.push_str(value),
                        None => match self.templates.get(UNKNOWN_NAME) {
                            Some(unknown) => out.push_str(unknown),
                            None => {
                                out.push('{');
                                out.push_str(name);
                                out.push('}');
                            }
                        },
                    }
                    rest = &after[close + 1..];
                }
                None => {
                    out.push_str(&rest[open..]);
                    rest = "";
                }
            }
        }
        out.push_str(rest);
        Some(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renders_params_and_unknown_names() {
        let lexicon = Lexicon::core_english();
        let line = Line::new("sage.said.other").with("text", "hello");
        assert_eq!(lexicon.render(&line).unwrap(), "someone says, \"hello\"");
        let line = line.with("actor", "Ada");
        assert_eq!(lexicon.render(&line).unwrap(), "Ada says, \"hello\"");
    }

    #[test]
    fn indexed_other_falls_back_to_other() {
        let lexicon = Lexicon::core_english();
        let line = Line::new("sage.said.other.3")
            .with("actor", "Ada")
            .with("text", "hi");
        assert_eq!(lexicon.render(&line).unwrap(), "Ada says, \"hi\"");
        assert!(lexicon.render(&Line::new("sage.said.self.3")).is_none());
    }

    #[test]
    fn world_override_wins_and_missing_key_renders_nothing() {
        let mut lexicon = Lexicon::core_english();
        lexicon.set("sage.go.where", "Which way?");
        assert_eq!(
            lexicon.render(&Line::new("sage.go.where")).unwrap(),
            "Which way?"
        );
        assert!(lexicon.render(&Line::new("sage.command.self")).is_none());
    }

    #[test]
    fn unclosed_brace_is_left_alone() {
        let mut lexicon = Lexicon::new();
        lexicon.set("x.y", "a {b");
        assert_eq!(lexicon.render(&Line::new("x.y")).unwrap(), "a {b");
    }
}
