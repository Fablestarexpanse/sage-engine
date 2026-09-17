//! Tavern character cards to SAGE agents.
//!
//! The mapping follows the founding blueprint: description and personality become the persona,
//! the scenario a goal, example messages the voice, and the lorebook seed memories. The card's
//! own prompt fields (`system_prompt`, `post_history_instructions`) are dropped: SAGE builds its
//! own prompt, and text from a card is only ever information for the model, never instructions.
//!
//! An imported agent is `hybrid`. With a model it thinks when spoken to. With no model it still
//! answers when addressed by name, or told something, with a line from its first message.
//! Nothing here depends on a model.

use sage_schema::card::{Card, Finding, Severity};
use serde::Serialize;

use crate::mind::{MAX_VOICE, MAX_VOICE_CHARS, Mind, Rule, THINK, When};

/// How often an imported agent thinks, in ticks.
pub const IMPORTED_THINK_EVERY: u64 = 10;

/// Most seed memories kept from a lorebook.
pub const MAX_SEED_MEMORIES: usize = 64;

/// Longest seed memory or goal, in characters.
pub const MAX_MEMORY_CHARS: usize = 1000;

/// Longest agent name, in characters.
pub const MAX_NAME_CHARS: usize = 64;

/// Longest short description, in characters.
pub const MAX_DESCRIPTION_CHARS: usize = 280;

/// Longest no-model greeting, in characters.
pub const MAX_GREETING_CHARS: usize = 200;

/// Longest persona `sage.mind` accepts, in characters.
const MAX_PERSONA_CHARS: usize = 4000;

/// Who `{{user}}` becomes: in a shared world there is no single user.
const USER: &str = "someone";

/// An agent made from a card, ready to be placed in a world.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct ImportedAgent {
    /// `sage.describable` name.
    pub name: String,
    /// `sage.describable` description: a short line others see.
    pub description: String,
    /// `sage.mind`.
    pub mind: Mind,
    /// Memories the agent starts with, from the card's lorebook.
    pub seed_memories: Vec<String>,
}

/// Converts a card. Every change or loss is reported; nothing is dropped silently.
pub fn agent_from_card(card: &Card) -> (ImportedAgent, Vec<Finding>) {
    let mut findings = Vec::new();
    let mut note = |severity, path: &str, message: String| {
        findings.push(Finding {
            severity,
            path: path.to_owned(),
            message,
        });
    };

    let collapsed = card.name.split_whitespace().collect::<Vec<_>>().join(" ");
    let (name, cut) = clip(&collapsed, MAX_NAME_CHARS);
    if cut {
        note(
            Severity::Warning,
            "card.name",
            format!("shortened to {MAX_NAME_CHARS} characters"),
        );
    }
    let fill = |text: &str| fill_macros(text, &name);

    let description_text = fill(&card.description);
    let first_paragraph = description_text
        .split("\n\n")
        .map(str::trim)
        .find(|p| !p.is_empty())
        .unwrap_or_default()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let (description, _) = clip(&first_paragraph, MAX_DESCRIPTION_CHARS);

    let mut persona = description_text.trim().to_owned();
    let personality = fill(&card.personality);
    if !personality.trim().is_empty() {
        if !persona.is_empty() {
            persona.push_str("\n\n");
        }
        persona.push_str("Personality: ");
        persona.push_str(personality.trim());
    }
    let (persona, cut) = clip(&persona, MAX_PERSONA_CHARS);
    if cut {
        note(
            Severity::Warning,
            "card.description",
            format!(
                "description and personality together were shortened to {MAX_PERSONA_CHARS} characters"
            ),
        );
    }

    let mut goals = Vec::new();
    let scenario = fill(&card.scenario);
    if !scenario.trim().is_empty() {
        let (goal, cut) = clip(scenario.trim(), MAX_MEMORY_CHARS);
        if cut {
            note(
                Severity::Warning,
                "card.scenario",
                format!("shortened to {MAX_MEMORY_CHARS} characters"),
            );
        }
        goals.push(goal);
    }

    let examples = split_examples(&fill(&card.mes_example));
    let mut voice = Vec::new();
    for (i, example) in examples.iter().enumerate() {
        if voice.len() == MAX_VOICE {
            note(
                Severity::Warning,
                "card.mes_example",
                format!("kept the first {MAX_VOICE} of {} examples", examples.len()),
            );
            break;
        }
        let (kept, cut) = clip(example, MAX_VOICE_CHARS);
        if cut {
            note(
                Severity::Warning,
                "card.mes_example",
                format!(
                    "example {} shortened to {MAX_VOICE_CHARS} characters",
                    i + 1
                ),
            );
        }
        voice.push(kept);
    }
    let first_mes = fill(&card.first_mes);
    if voice.is_empty() && !first_mes.trim().is_empty() {
        voice.push(clip(first_mes.trim(), MAX_VOICE_CHARS).0);
    }

    let mut rules = vec![
        Rule {
            when: When {
                heard: Some("sage.said".into()),
                ..When::default()
            },
            command: THINK.into(),
        },
        Rule {
            when: When {
                heard: Some("sage.dialogue.told".into()),
                ..When::default()
            },
            command: THINK.into(),
        },
    ];
    match greeting(&first_mes) {
        Some(greeting) => {
            let first_name = name
                .split_whitespace()
                .next()
                .unwrap_or_default()
                .to_lowercase();
            rules.push(Rule {
                when: When {
                    heard: Some("sage.said".into()),
                    text_contains: Some(first_name),
                    ..When::default()
                },
                command: format!("say {greeting}"),
            });
            rules.push(Rule {
                when: When {
                    heard: Some("sage.dialogue.told".into()),
                    ..When::default()
                },
                command: format!("tell {{speaker}} {greeting}"),
            });
        }
        None => note(
            Severity::Note,
            "card.first_mes",
            "no spoken line found; without a model this agent stays silent".into(),
        ),
    }

    let mut seed_memories = Vec::new();
    if let Some(book) = &card.character_book {
        let mut disabled = 0;
        for (i, entry) in book.entries.iter().enumerate() {
            let content = fill(&entry.content);
            if !entry.enabled {
                disabled += 1;
                continue;
            }
            if content.trim().is_empty() {
                continue;
            }
            if seed_memories.len() == MAX_SEED_MEMORIES {
                note(
                    Severity::Warning,
                    "card.character_book",
                    format!("kept the first {MAX_SEED_MEMORIES} entries as memories"),
                );
                break;
            }
            let (memory, cut) = clip(content.trim(), MAX_MEMORY_CHARS);
            if cut {
                note(
                    Severity::Warning,
                    &format!("card.character_book.entries[{i}]"),
                    format!("shortened to {MAX_MEMORY_CHARS} characters"),
                );
            }
            seed_memories.push(memory);
        }
        if disabled > 0 {
            note(
                Severity::Note,
                "card.character_book",
                format!("disabled entries not imported: {disabled}"),
            );
        }
    }

    for (path, text) in [
        ("card.system_prompt", &card.system_prompt),
        (
            "card.post_history_instructions",
            &card.post_history_instructions,
        ),
    ] {
        if !text.trim().is_empty() {
            note(
                Severity::Warning,
                path,
                "not imported: SAGE builds its own prompt, and card text never reaches the model as instructions".into(),
            );
        }
    }
    if !card.alternate_greetings.is_empty() {
        note(
            Severity::Note,
            "card.alternate_greetings",
            format!(
                "alternate greetings not imported: {}",
                card.alternate_greetings.len()
            ),
        );
    }
    let leftover = [
        &card.description,
        &card.personality,
        &card.scenario,
        &card.first_mes,
        &card.mes_example,
    ]
    .iter()
    .any(|t| unknown_macro(&fill_macros(t, &name)));
    if leftover {
        note(
            Severity::Note,
            "card",
            "macros other than {{char}} and {{user}} were left as written".into(),
        );
    }

    let mind = Mind {
        driver: "hybrid".into(),
        think_every: IMPORTED_THINK_EVERY,
        persona,
        goals,
        rules,
        importance: Default::default(),
        reflect_threshold: None,
        voice,
    };
    if let Err(e) = sage_core::Component::validate(&mind) {
        note(
            Severity::Error,
            "mind",
            format!("the converted mind is not valid: {e}"),
        );
    }
    (
        ImportedAgent {
            name,
            description,
            mind,
            seed_memories,
        },
        findings,
    )
}

/// Replaces `{{char}}` and `<BOT>` with the name, and `{{user}}` and `<USER>` with a neutral
/// word, ignoring case.
pub fn fill_macros(text: &str, name: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    'scan: while !rest.is_empty() {
        for (pattern, value) in [
            ("{{char}}", name),
            ("{{user}}", USER),
            ("<bot>", name),
            ("<user>", USER),
        ] {
            if rest.len() >= pattern.len()
                && rest.is_char_boundary(pattern.len())
                && rest[..pattern.len()].eq_ignore_ascii_case(pattern)
            {
                out.push_str(value);
                rest = &rest[pattern.len()..];
                continue 'scan;
            }
        }
        let c = rest.chars().next().expect("not empty");
        out.push(c);
        rest = &rest[c.len_utf8()..];
    }
    out
}

fn unknown_macro(text: &str) -> bool {
    text.find("{{")
        .is_some_and(|start| text[start..].contains("}}"))
}

/// Example exchanges, split on `<START>`.
fn split_examples(text: &str) -> Vec<String> {
    let lower = text.to_ascii_lowercase();
    let mut parts = Vec::new();
    let mut from = 0;
    while let Some(at) = lower[from..].find("<start>") {
        parts.push(&text[from..from + at]);
        from += at + "<start>".len();
    }
    parts.push(&text[from..]);
    parts
        .into_iter()
        .map(str::trim)
        .filter(|p| !p.is_empty())
        .map(str::to_owned)
        .collect()
}

/// A short spoken line from a first message: actions in `*asterisks*` removed, braces removed
/// (they would read as rule variables), whitespace collapsed, cut at a sentence end if one
/// fits.
fn greeting(first_mes: &str) -> Option<String> {
    let mut spoken = String::new();
    let mut in_action = false;
    for c in first_mes.chars() {
        match c {
            '*' => in_action = !in_action,
            '{' | '}' => {}
            _ if !in_action => spoken.push(c),
            _ => {}
        }
    }
    // When there is quoted speech, only the quotes are spoken; the rest is narration.
    let mut quoted = Vec::new();
    let mut current: Option<String> = None;
    for c in spoken.chars() {
        match (c, current.as_mut()) {
            ('"' | '\u{201c}', None) => current = Some(String::new()),
            ('"' | '\u{201d}', Some(_)) => quoted.extend(current.take()),
            (_, Some(text)) => text.push(c),
            _ => {}
        }
    }
    let spoken = if quoted.is_empty() {
        spoken.replace(['"', '\u{201c}', '\u{201d}'], "")
    } else {
        quoted.join(" ")
    };
    let spoken = spoken.split_whitespace().collect::<Vec<_>>().join(" ");
    let spoken = spoken
        .trim_matches(|c: char| matches!(c, '"' | '\u{201c}' | '\u{201d}') || c.is_whitespace());
    if spoken.is_empty() {
        return None;
    }
    if spoken.chars().count() <= MAX_GREETING_CHARS {
        return Some(spoken.to_owned());
    }
    let head: String = spoken.chars().take(MAX_GREETING_CHARS).collect();
    if let Some(end) = head.rfind(['.', '!', '?'])
        && end > 0
    {
        return Some(head[..=end].to_owned());
    }
    Some(clip(spoken, MAX_GREETING_CHARS).0)
}

/// At most `max` characters, cut at a word boundary when one is near, with `…` when cut.
fn clip(text: &str, max: usize) -> (String, bool) {
    if text.chars().count() <= max {
        return (text.to_owned(), false);
    }
    let head: String = text.chars().take(max.saturating_sub(1)).collect();
    let cut = match head.rfind(char::is_whitespace) {
        Some(at) if at * 4 >= head.len() * 3 => head[..at].trim_end().to_owned(),
        _ => head,
    };
    (format!("{cut}…"), true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn macros_are_filled_ignoring_case() {
        assert_eq!(
            fill_macros(
                "{{Char}} meets {{USER}}; <bot> and <User>. {{random}}",
                "Maren"
            ),
            "Maren meets someone; Maren and someone. {{random}}"
        );
        assert_eq!(fill_macros("é{{char}}ü", "Zoë"), "éZoëü");
    }

    #[test]
    fn greetings_drop_actions_and_fit() {
        assert_eq!(
            greeting("*looks up* \"Another one?\" *sighs*").as_deref(),
            Some("Another one?")
        );
        assert_eq!(greeting("*only an action*"), None);
        let long = format!("{}. {}", "a".repeat(150), "b".repeat(100));
        assert_eq!(greeting(&long).unwrap(), format!("{}.", "a".repeat(150)));
        assert_eq!(greeting("{speaker} hi").as_deref(), Some("speaker hi"));
        // Found by the real run: speech split by an action kept the quotes between.
        assert_eq!(
            greeting("*She doesn't look up.* \"Three coins. Fog's extra.\" *Taps.* \"Name?\"")
                .as_deref(),
            Some("Three coins. Fog's extra. Name?")
        );
        assert_eq!(
            greeting("He nods. \u{201c}Evening.\u{201d} Then silence.").as_deref(),
            Some("Evening.")
        );
        // An unclosed quote is not speech.
        assert_eq!(greeting("Well \"then").as_deref(), Some("Well then"));
    }

    #[test]
    fn clipping_counts_characters_and_marks_the_cut() {
        assert_eq!(clip("short", 10), ("short".into(), false));
        let (cut, was) = clip("one two three four five", 12);
        assert!(was);
        assert!(cut.chars().count() <= 12, "{cut}");
        assert!(cut.ends_with('…'));
        let (cut, _) = clip(&"月".repeat(20), 5);
        assert_eq!(cut.chars().count(), 5);
    }

    #[test]
    fn examples_split_on_start() {
        assert_eq!(
            split_examples("<START>\na\n<start>\n\nb\n<START>"),
            ["a", "b"]
        );
    }
}
