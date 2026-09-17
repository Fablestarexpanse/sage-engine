//! Character cards: Tavern Card v1, v2 and v3, read from PNG text chunks or JSON.
//!
//! **Shape first, label second.** Every recognized chunk is decoded, and the kind of card is
//! inferred from the payload's shape. A label that disagrees with the shape is reported,
//! never trusted. Nothing here panics on any input; every problem becomes a [`Finding`].
//!
//! Chunks read: `ccv3` (v3) and `chara` (v2, or anything older). When both hold a usable
//! card, `ccv3` wins, as the v3 specification says.

use base64::Engine as _;
use base64::engine::{DecodePaddingMode, GeneralPurpose, GeneralPurposeConfig};
use serde::Serialize;
use serde_json::{Map, Value};

use crate::png;

/// Largest decoded card payload read, in bytes. Real cards with big lorebooks run to a few
/// MiB; SAGE's own cards stay under 1 MiB.
pub const MAX_CARD_BYTES: usize = 4 * 1024 * 1024;

/// Largest PNG read, in bytes.
pub const MAX_PNG_BYTES: usize = 64 * 1024 * 1024;

/// Keywords whose chunks may hold a card.
pub const CARD_KEYWORDS: [&str; 2] = ["ccv3", "chara"];

/// How serious a finding is.
#[derive(Serialize, Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    /// The card cannot be used.
    Error,
    /// The card is usable, but something was dropped, changed or looks wrong.
    Warning,
    /// Worth knowing; nothing was lost.
    Note,
}

/// One thing found while reading a card.
#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
pub struct Finding {
    /// How serious.
    pub severity: Severity,
    /// Where: a chunk (`chunk:chara`), or a JSON path (`data.character_book.entries[2].keys`).
    pub path: String,
    /// What, in plain words.
    pub message: String,
}

/// Which card specification a payload follows, judged by its shape.
#[derive(Serialize, Clone, Copy, Debug, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Spec {
    /// Flat fields, no `spec`.
    V1,
    /// `spec: chara_card_v2`.
    V2,
    /// `spec: chara_card_v3`.
    V3,
}

/// A character card, normalized across versions. Text is exactly as written, macros
/// (`{{char}}`, `{{user}}`) included.
#[derive(Serialize, Clone, Debug, PartialEq, Default)]
pub struct Card {
    /// Character name.
    pub name: String,
    /// Description.
    pub description: String,
    /// Personality summary.
    pub personality: String,
    /// Scenario.
    pub scenario: String,
    /// First message.
    pub first_mes: String,
    /// Example messages, `<START>`-separated.
    pub mes_example: String,
    /// Other first messages.
    pub alternate_greetings: Vec<String>,
    /// Prompt override the card asks for.
    pub system_prompt: String,
    /// Instructions the card asks to put after history.
    pub post_history_instructions: String,
    /// Notes for people, not the model.
    pub creator_notes: String,
    /// Tags.
    pub tags: Vec<String>,
    /// Creator as written in the card.
    pub creator: String,
    /// The card's own version string.
    pub character_version: String,
    /// Embedded lorebook.
    pub character_book: Option<Book>,
}

/// A lorebook.
#[derive(Serialize, Clone, Debug, PartialEq, Default)]
pub struct Book {
    /// Name, if given.
    pub name: String,
    /// Entries in file order.
    pub entries: Vec<BookEntry>,
}

/// One lorebook entry.
#[derive(Serialize, Clone, Debug, PartialEq, Default)]
pub struct BookEntry {
    /// Trigger keys.
    pub keys: Vec<String>,
    /// The lore.
    pub content: String,
    /// Whether the entry is on.
    pub enabled: bool,
    /// Entry name or comment.
    pub comment: String,
}

/// The result of reading a card.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct CardReport {
    /// Whether a usable card was found (no errors).
    pub ok: bool,
    /// Where the card came from: `chunk:ccv3`, `chunk:chara`, or `json`.
    pub source: Option<String>,
    /// The card's specification, by shape.
    pub spec: Option<Spec>,
    /// Everything found, errors first, then in reading order.
    pub findings: Vec<Finding>,
    /// The card, when one was usable.
    pub card: Option<Card>,
}

struct Findings(Vec<Finding>);

impl Findings {
    fn push(&mut self, severity: Severity, path: impl Into<String>, message: impl Into<String>) {
        self.0.push(Finding {
            severity,
            path: path.into(),
            message: message.into(),
        });
    }

    fn has_errors(&self) -> bool {
        self.0.iter().any(|f| f.severity == Severity::Error)
    }
}

fn finish(
    mut findings: Findings,
    source: Option<String>,
    parsed: Option<(Spec, Card)>,
) -> CardReport {
    // Stable: errors, then warnings, then notes, each in the order found.
    findings.0.sort_by_key(|f| f.severity);
    let ok = parsed.is_some() && !findings.has_errors();
    let (spec, card) = match parsed {
        Some((spec, card)) => (Some(spec), Some(card)),
        None => (None, None),
    };
    CardReport {
        ok,
        source,
        spec,
        findings: findings.0,
        card,
    }
}

/// Reads a card from PNG bytes.
pub fn read_png(bytes: &[u8]) -> CardReport {
    let mut findings = Findings(Vec::new());
    if bytes.len() > MAX_PNG_BYTES {
        findings.push(
            Severity::Error,
            "",
            format!("the file is over {} MiB", MAX_PNG_BYTES / (1024 * 1024)),
        );
        return finish(findings, None, None);
    }
    let (texts, ending) = match png::text_chunks(bytes) {
        Ok(found) => found,
        Err(e) => {
            findings.push(Severity::Error, "", e.to_string());
            return finish(findings, None, None);
        }
    };
    match ending {
        png::Ending::Iend => {}
        png::Ending::NoIend => findings.push(Severity::Warning, "", "the PNG has no IEND chunk"),
        // A cut-off download often still holds the whole card, which comes before the pixels.
        png::Ending::Damaged(e) => findings.push(
            Severity::Warning,
            "",
            format!("the file is damaged ({e}); only the chunks before it were read"),
        ),
    }

    let mut candidates: Vec<(String, Spec, Card, Findings)> = Vec::new();
    for text in &texts {
        let keyword = text.keyword.as_str();
        let known = CARD_KEYWORDS.contains(&keyword);
        if !known {
            if CARD_KEYWORDS.contains(&keyword.to_ascii_lowercase().as_str()) {
                findings.push(
                    Severity::Warning,
                    format!("chunk:{keyword}"),
                    "keyword differs from a card keyword only in case; not read",
                );
            } else if keyword == "sage" {
                findings.push(
                    Severity::Note,
                    "chunk:sage",
                    "a SAGE fragment chunk is present; this reader does not use it yet",
                );
            }
            continue;
        }
        let path = format!("chunk:{keyword}");
        if !text.crc_ok {
            findings.push(Severity::Warning, &path, "the chunk's CRC does not match");
        }
        let Some(raw) = text.text else {
            findings.push(
                Severity::Warning,
                &path,
                "the text is compressed; compressed card chunks are not read",
            );
            continue;
        };
        let mut own = Findings(Vec::new());
        let Some(json) = decode_payload(raw, &path, &mut own) else {
            findings.0.extend(own.0);
            continue;
        };
        match parse_json(&json, &path, &mut own) {
            Some((spec, card)) => {
                let expected = if keyword == "ccv3" {
                    Spec::V3
                } else {
                    Spec::V2
                };
                if spec != expected && !(keyword == "chara" && spec == Spec::V1) {
                    own.push(
                        Severity::Warning,
                        &path,
                        format!(
                            "chunk `{keyword}` holds a {} card; read by its shape",
                            spec_name(spec)
                        ),
                    );
                }
                candidates.push((keyword.to_owned(), spec, card, own));
            }
            None => findings.0.extend(own.0),
        }
    }

    if candidates.is_empty() {
        if !findings.has_errors() {
            findings.push(Severity::Error, "", "no character card found in this PNG");
        }
        return finish(findings, None, None);
    }
    // Prefer ccv3, then the newest shape.
    candidates
        .sort_by_key(|(keyword, spec, _, _)| (keyword != "ccv3", std::cmp::Reverse(*spec as u8)));
    let mut rest = candidates.split_off(1);
    let (keyword, spec, card, own) = candidates.pop().expect("one candidate");
    findings.0.extend(own.0);
    for (other, _, other_card, _) in rest.drain(..) {
        if other_card.name != card.name {
            findings.push(
                Severity::Warning,
                format!("chunk:{other}"),
                format!(
                    "also holds a card named `{}`, which differs from the `{}` read from `{keyword}`",
                    other_card.name, card.name
                ),
            );
        } else {
            findings.push(
                Severity::Note,
                format!("chunk:{other}"),
                format!("also holds a card; `{keyword}` was read"),
            );
        }
    }
    finish(
        findings,
        Some(format!("chunk:{keyword}")),
        Some((spec, card)),
    )
}

/// Reads a card from JSON bytes, as exported by card tools.
pub fn read_json(bytes: &[u8]) -> CardReport {
    let mut findings = Findings(Vec::new());
    if bytes.len() > MAX_CARD_BYTES {
        findings.push(
            Severity::Error,
            "",
            format!("the card is over {} MiB", MAX_CARD_BYTES / (1024 * 1024)),
        );
        return finish(findings, None, None);
    }
    let parsed = parse_json(bytes, "", &mut findings);
    finish(
        findings,
        parsed.is_some().then(|| "json".to_owned()),
        parsed,
    )
}

fn spec_name(spec: Spec) -> &'static str {
    match spec {
        Spec::V1 => "v1",
        Spec::V2 => "v2",
        Spec::V3 => "v3",
    }
}

/// Base64 (the usual form) or raw JSON (some tools) to JSON bytes.
fn decode_payload(raw: &[u8], path: &str, findings: &mut Findings) -> Option<Vec<u8>> {
    let trimmed = raw.trim_ascii();
    if trimmed.first() == Some(&b'{') {
        findings.push(
            Severity::Note,
            path,
            "the payload is plain JSON, not Base64",
        );
        return check_size(trimmed.to_vec(), path, findings);
    }
    // Base64 is 4 bytes per 3; refuse before decoding anything too big.
    if trimmed.len() / 4 * 3 > MAX_CARD_BYTES + 3 {
        findings.push(
            Severity::Error,
            path,
            format!("the payload is over {} MiB", MAX_CARD_BYTES / (1024 * 1024)),
        );
        return None;
    }
    let compact: Vec<u8> = trimmed
        .iter()
        .copied()
        .filter(|b| !b.is_ascii_whitespace())
        .collect();
    const BASE64: GeneralPurpose = GeneralPurpose::new(
        &base64::alphabet::STANDARD,
        GeneralPurposeConfig::new().with_decode_padding_mode(DecodePaddingMode::Indifferent),
    );
    match BASE64.decode(&compact) {
        Ok(json) => check_size(json, path, findings),
        Err(e) => {
            findings.push(
                Severity::Error,
                path,
                format!("the payload is neither Base64 nor JSON: {e}"),
            );
            None
        }
    }
}

fn check_size(json: Vec<u8>, path: &str, findings: &mut Findings) -> Option<Vec<u8>> {
    if json.len() > MAX_CARD_BYTES {
        findings.push(
            Severity::Error,
            path,
            format!("the payload is over {} MiB", MAX_CARD_BYTES / (1024 * 1024)),
        );
        return None;
    }
    Some(json)
}

fn parse_json(bytes: &[u8], path: &str, findings: &mut Findings) -> Option<(Spec, Card)> {
    let bytes = bytes.strip_prefix(b"\xef\xbb\xbf").unwrap_or(bytes);
    let value: Value = match serde_json::from_slice(bytes) {
        Ok(value) => value,
        Err(e) => {
            findings.push(
                Severity::Error,
                path,
                format!("the payload is not valid JSON: {e}"),
            );
            return None;
        }
    };
    let Some(object) = value.as_object() else {
        findings.push(Severity::Error, path, "the payload is not a JSON object");
        return None;
    };
    let join = |field: &str| {
        if path.is_empty() {
            field.to_owned()
        } else {
            format!("{path}:{field}")
        }
    };

    let spec = match object.get("spec").and_then(Value::as_str) {
        Some("chara_card_v3") => Spec::V3,
        Some("chara_card_v2") => Spec::V2,
        Some("lorebook_v3") => {
            findings.push(
                Severity::Error,
                join("spec"),
                "this is a lorebook, not a character card",
            );
            return None;
        }
        Some(other) => {
            findings.push(
                Severity::Error,
                join("spec"),
                format!("unknown card specification `{other}`"),
            );
            return None;
        }
        None if object.contains_key("entries") && !object.contains_key("name") => {
            findings.push(
                Severity::Error,
                path,
                "this looks like a lorebook, not a character card",
            );
            return None;
        }
        None if ["name", "char_name"]
            .iter()
            .any(|k| object.contains_key(*k)) =>
        {
            Spec::V1
        }
        None => {
            findings.push(
                Severity::Error,
                path,
                "not a character card: no `spec` and no `name`",
            );
            return None;
        }
    };

    let (data, data_path) = match spec {
        Spec::V1 => (object, join("")),
        Spec::V2 | Spec::V3 => match object.get("data").and_then(Value::as_object) {
            Some(data) => (data, join("data.")),
            None => {
                findings.push(
                    Severity::Error,
                    join("data"),
                    "a v2 or v3 card needs a `data` object",
                );
                return None;
            }
        },
    };
    let mut fields = Fields {
        data,
        prefix: data_path,
        findings,
    };

    let mut card = Card {
        name: fields.text(&["name", "char_name"]),
        description: fields.text(&["description", "char_persona"]),
        personality: fields.text(&["personality"]),
        scenario: fields.text(&["scenario", "world_scenario"]),
        first_mes: fields.text(&["first_mes", "char_greeting"]),
        mes_example: fields.text(&["mes_example", "example_dialogue"]),
        ..Card::default()
    };
    if spec != Spec::V1 {
        card.alternate_greetings = fields.texts("alternate_greetings");
        card.system_prompt = fields.text(&["system_prompt"]);
        card.post_history_instructions = fields.text(&["post_history_instructions"]);
        card.creator_notes = fields.text(&["creator_notes"]);
        card.tags = fields.texts("tags");
        card.creator = fields.text(&["creator"]);
        card.character_version = fields.text(&["character_version"]);
        card.character_book = fields.book();
    }
    if card.name.trim().is_empty() {
        fields.findings.push(
            Severity::Error,
            format!("{}name", fields.prefix),
            "the card has no name",
        );
    }
    Some((spec, card))
}

struct Fields<'a, 'f> {
    data: &'a Map<String, Value>,
    prefix: String,
    findings: &'f mut Findings,
}

impl Fields<'_, '_> {
    /// The first of `names` that is present; a present value that is not a string is reported
    /// and read as empty.
    fn text(&mut self, names: &[&str]) -> String {
        for (i, name) in names.iter().enumerate() {
            match self.data.get(*name) {
                None | Some(Value::Null) => continue,
                Some(Value::String(s)) => {
                    if i > 0 {
                        self.findings.push(
                            Severity::Note,
                            format!("{}{name}", self.prefix),
                            format!("read as `{}` (an older field name)", names[0]),
                        );
                    }
                    return s.clone();
                }
                Some(_) => {
                    self.findings.push(
                        Severity::Warning,
                        format!("{}{name}", self.prefix),
                        "expected text; ignored",
                    );
                    return String::new();
                }
            }
        }
        String::new()
    }

    fn texts(&mut self, name: &str) -> Vec<String> {
        let path = format!("{}{name}", self.prefix);
        strings(self.data.get(name), &path, self.findings)
    }

    fn book(&mut self) -> Option<Book> {
        let path = format!("{}character_book", self.prefix);
        let value = self.data.get("character_book")?;
        if value.is_null() {
            return None;
        }
        let Some(book) = value.as_object() else {
            self.findings.push(
                Severity::Warning,
                path,
                "expected a lorebook object; ignored",
            );
            return None;
        };
        let name = book
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        // Array in the card specifications; an object keyed by number in world-info exports.
        let listed: Vec<(String, &Value)> = match book.get("entries") {
            Some(Value::Array(items)) => items
                .iter()
                .enumerate()
                .map(|(i, v)| (format!("{path}.entries[{i}]"), v))
                .collect(),
            Some(Value::Object(items)) => items
                .iter()
                .map(|(k, v)| (format!("{path}.entries.{k}"), v))
                .collect(),
            None | Some(Value::Null) => Vec::new(),
            Some(_) => {
                self.findings.push(
                    Severity::Warning,
                    format!("{path}.entries"),
                    "expected a list of entries; ignored",
                );
                Vec::new()
            }
        };
        let mut entries = Vec::with_capacity(listed.len());
        for (entry_path, value) in listed {
            let Some(entry) = value.as_object() else {
                self.findings.push(
                    Severity::Warning,
                    entry_path,
                    "expected an entry object; skipped",
                );
                continue;
            };
            let keys_value = entry.get("keys").or_else(|| entry.get("key"));
            let content = match entry.get("content") {
                Some(Value::String(s)) => s.clone(),
                None | Some(Value::Null) => String::new(),
                Some(_) => {
                    self.findings.push(
                        Severity::Warning,
                        format!("{entry_path}.content"),
                        "expected text; ignored",
                    );
                    String::new()
                }
            };
            let enabled = match (entry.get("enabled"), entry.get("disable")) {
                (Some(Value::Bool(enabled)), _) => *enabled,
                (_, Some(Value::Bool(disabled))) => !disabled,
                _ => true,
            };
            let comment = ["comment", "name"]
                .iter()
                .find_map(|k| entry.get(*k).and_then(Value::as_str))
                .unwrap_or_default()
                .to_owned();
            entries.push(BookEntry {
                keys: strings(keys_value, &format!("{entry_path}.keys"), self.findings),
                content,
                enabled,
                comment,
            });
        }
        Some(Book { name, entries })
    }
}

fn strings(value: Option<&Value>, path: &str, findings: &mut Findings) -> Vec<String> {
    match value {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => {
            let mut out = Vec::with_capacity(items.len());
            let mut skipped = 0;
            for item in items {
                match item.as_str() {
                    Some(s) => out.push(s.to_owned()),
                    None => skipped += 1,
                }
            }
            if skipped > 0 {
                findings.push(
                    Severity::Warning,
                    path,
                    format!("{skipped} item(s) were not text; skipped"),
                );
            }
            out
        }
        Some(_) => {
            findings.push(Severity::Warning, path, "expected a list of text; ignored");
            Vec::new()
        }
    }
}
