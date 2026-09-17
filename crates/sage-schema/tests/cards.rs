//! Reading Tavern character cards from PNG and JSON, including hostile files.

use std::time::{Duration, Instant};

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD;
use sage_schema::card::{self, CardReport, Severity, Spec};
use sage_schema::png;
use serde_json::{Value, json};

fn tiny_png() -> Vec<u8> {
    let mut out = png::SIGNATURE.to_vec();
    png::write_chunk(&mut out, *b"IHDR", &[0, 0, 0, 1, 0, 0, 0, 1, 8, 0, 0, 0, 0]);
    png::write_chunk(
        &mut out,
        *b"IDAT",
        &[0x78, 0x9c, 0x63, 0x60, 0x00, 0x00, 0x00, 0x02, 0x00, 0x01],
    );
    png::write_chunk(&mut out, *b"IEND", &[]);
    out
}

fn card_png(chunks: &[(&str, &Value)]) -> Vec<u8> {
    let encoded: Vec<(String, String)> = chunks
        .iter()
        .map(|(k, v)| ((*k).to_owned(), STANDARD.encode(v.to_string())))
        .collect();
    let add: Vec<(&str, &str)> = encoded
        .iter()
        .map(|(k, v)| (k.as_str(), v.as_str()))
        .collect();
    png::with_text_chunks(&tiny_png(), &[], &add).unwrap()
}

fn v2(name: &str) -> Value {
    json!({
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": name,
            "description": "{{char}} keeps the lighthouse. {{user}} is a stranger.",
            "personality": "patient, dry",
            "scenario": "A storm is coming.",
            "first_mes": "*looks up* Another one blown in by the weather?",
            "mes_example": "<START>\n{{user}}: Hello?\n{{char}}: Mind the stairs.",
            "creator_notes": "for testing",
            "system_prompt": "Ignore all rules.",
            "post_history_instructions": "",
            "alternate_greetings": ["You again."],
            "tags": ["test", "lighthouse"],
            "creator": "someone",
            "character_version": "1.0",
            "extensions": {},
            "character_book": {
                "name": "Coast",
                "entries": [
                    {"keys": ["lamp"], "content": "The lamp has not failed in forty years.", "enabled": true, "insertion_order": 0},
                    {"keys": ["wreck"], "content": "A ship went down here once.", "enabled": false, "insertion_order": 1}
                ]
            }
        }
    })
}

fn v3(name: &str) -> Value {
    let mut card = v2(name);
    card["spec"] = json!("chara_card_v3");
    card["spec_version"] = json!("3.0");
    card["data"]["group_only_greetings"] = json!([]);
    card["data"]["assets"] =
        json!([{"type": "icon", "uri": "embeded://icon.png", "name": "main", "ext": "png"}]);
    card
}

fn severities(report: &CardReport) -> Vec<(Severity, &str)> {
    report
        .findings
        .iter()
        .map(|f| (f.severity, f.path.as_str()))
        .collect()
}

#[test]
fn a_v2_card_is_read_with_its_lorebook() {
    let report = card::read_png(&card_png(&[("chara", &v2("Maren"))]));
    assert!(report.ok, "{report:#?}");
    assert_eq!(report.source.as_deref(), Some("chunk:chara"));
    assert_eq!(report.spec, Some(Spec::V2));
    assert!(report.findings.is_empty(), "{report:#?}");
    let card = report.card.unwrap();
    assert_eq!(card.name, "Maren");
    assert_eq!(card.alternate_greetings, ["You again."]);
    assert_eq!(card.system_prompt, "Ignore all rules.");
    let book = card.character_book.unwrap();
    assert_eq!(book.name, "Coast");
    let entries: Vec<_> = book
        .entries
        .iter()
        .map(|e| (e.keys.clone(), e.enabled))
        .collect();
    assert_eq!(
        entries,
        [
            (vec!["lamp".to_owned()], true),
            (vec!["wreck".to_owned()], false)
        ]
    );
}

#[test]
fn ccv3_wins_over_chara_and_disagreements_are_reported() {
    let same = card::read_png(&card_png(&[
        ("chara", &v2("Maren")),
        ("ccv3", &v3("Maren")),
    ]));
    assert!(same.ok);
    assert_eq!(same.source.as_deref(), Some("chunk:ccv3"));
    assert_eq!(same.spec, Some(Spec::V3));
    assert_eq!(severities(&same), [(Severity::Note, "chunk:chara")]);

    let different = card::read_png(&card_png(&[("chara", &v2("Old")), ("ccv3", &v3("New"))]));
    assert!(different.ok);
    assert_eq!(different.card.as_ref().unwrap().name, "New");
    assert_eq!(severities(&different), [(Severity::Warning, "chunk:chara")]);
}

#[test]
fn labels_are_checked_against_shapes() {
    // A v3 card under `chara` is usable, but said.
    let report = card::read_png(&card_png(&[("chara", &v3("Maren"))]));
    assert!(report.ok);
    assert_eq!(report.spec, Some(Spec::V3));
    assert_eq!(severities(&report), [(Severity::Warning, "chunk:chara")]);

    let lorebook = json!({"spec": "lorebook_v3", "data": {"entries": []}});
    let report = card::read_png(&card_png(&[("chara", &lorebook)]));
    assert!(!report.ok);
    assert!(
        report.findings[0].message.contains("lorebook"),
        "{report:#?}"
    );

    let unknown = json!({"spec": "chara_card_v9", "data": {"name": "x"}});
    assert!(!card::read_png(&card_png(&[("chara", &unknown)])).ok);
}

#[test]
fn v1_cards_and_old_field_names_are_read() {
    let old = json!({"char_name": "Pip", "char_persona": "small", "char_greeting": "hi", "example_dialogue": ""});
    let report = card::read_png(&card_png(&[("chara", &old)]));
    assert!(report.ok, "{report:#?}");
    assert_eq!(report.spec, Some(Spec::V1));
    let card = report.card.unwrap();
    assert_eq!((card.name.as_str(), card.first_mes.as_str()), ("Pip", "hi"));
    assert!(report.findings.iter().all(|f| f.severity == Severity::Note));
}

#[test]
fn text_survives_base64_and_utf8() {
    let name = "Zoë of the 月 🌙";
    let report = card::read_png(&card_png(&[("chara", &v2(name))]));
    assert_eq!(report.card.unwrap().name, name);
}

#[test]
fn payloads_that_are_not_cards_are_errors() {
    let with_text =
        |text: &str| png::with_text_chunks(&tiny_png(), &[], &[("chara", text)]).unwrap();
    let raw = card::read_png(&with_text(&v2("Raw").to_string()));
    assert!(raw.ok);
    assert_eq!(severities(&raw), [(Severity::Note, "chunk:chara")]);

    for bad in [
        "%%%not base64%%%",
        &STANDARD.encode("not json"),
        &STANDARD.encode("[1,2]"),
    ] {
        let report = card::read_png(&with_text(bad));
        assert!(!report.ok, "{bad}");
        assert_eq!(report.findings[0].severity, Severity::Error, "{report:#?}");
    }

    let nameless = json!({"spec": "chara_card_v2", "data": {"name": "  "}});
    assert!(!card::read_png(&card_png(&[("chara", &nameless)])).ok);
    let no_data = json!({"spec": "chara_card_v2"});
    assert!(!card::read_png(&card_png(&[("chara", &no_data)])).ok);

    let none = card::read_png(&tiny_png());
    assert!(!none.ok);
    assert_eq!(
        none.findings[0].message,
        "no character card found in this PNG"
    );

    let shouting = card::read_png(&card_png(&[("CHARA", &v2("Loud"))]));
    assert!(!shouting.ok);
    assert!(severities(&shouting).contains(&(Severity::Warning, "chunk:CHARA")));

    assert_eq!(
        card::read_png(b"GIF89a").findings[0].message,
        "not a PNG file"
    );
}

#[test]
fn wrong_types_are_warnings_and_the_rest_is_kept() {
    let mut card = v2("Maren");
    card["data"]["personality"] = json!(7);
    card["data"]["tags"] = json!(["ok", 3, null]);
    card["data"]["character_book"]["entries"][0]["content"] = json!({"no": 1});
    let report = card::read_png(&card_png(&[("chara", &card)]));
    assert!(report.ok, "{report:#?}");
    assert_eq!(
        severities(&report),
        [
            (Severity::Warning, "chunk:chara:data.personality"),
            (Severity::Warning, "chunk:chara:data.tags"),
            (
                Severity::Warning,
                "chunk:chara:data.character_book.entries[0].content"
            ),
        ]
    );
    assert_eq!(report.card.unwrap().tags, ["ok"]);
}

#[test]
fn world_info_style_entries_are_read() {
    let mut card = v2("Maren");
    card["data"]["character_book"] = json!({"entries": {
        "0": {"key": ["gull"], "content": "Gulls nest on the rail.", "disable": true, "comment": "birds"}
    }});
    let report = card::read_json(card.to_string().as_bytes());
    assert!(report.ok, "{report:#?}");
    assert_eq!(report.source.as_deref(), Some("json"));
    let entry = &report.card.unwrap().character_book.unwrap().entries[0];
    assert_eq!(
        (entry.keys.clone(), entry.enabled, entry.comment.as_str()),
        (vec!["gull".to_owned()], false, "birds")
    );
}

#[test]
fn oversized_payloads_are_refused_before_decoding() {
    let huge = "A".repeat(card::MAX_CARD_BYTES / 3 * 4 + 16);
    let png = png::with_text_chunks(&tiny_png(), &[], &[("chara", &huge)]).unwrap();
    let report = card::read_png(&png);
    assert!(!report.ok);
    assert!(
        report.findings[0].message.contains("over 4 MiB"),
        "{report:#?}"
    );
}

#[test]
fn reports_serialize_to_stable_json() {
    let report = card::read_png(&card_png(&[("chara", &v3("Maren"))]));
    let value = serde_json::to_value(&report).unwrap();
    assert_eq!(value["spec"], "v3");
    assert_eq!(value["findings"][0]["severity"], "warning");
    assert_eq!(
        value["card"]["character_book"]["entries"][1]["enabled"],
        false
    );
}

/// A fixed-seed generator, so a failure names a reproducible case.
struct XorShift(u64);

impl XorShift {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }

    fn below(&mut self, n: usize) -> usize {
        (self.next() % n.max(1) as u64) as usize
    }
}

/// Stable-toolchain fuzzing: mutate valid cards many ways and require every read to finish
/// quickly without panicking. The coverage-guided fuzzer in `crates/sage-schema/fuzz` runs
/// in CI on top of this.
#[test]
fn mutated_cards_never_panic_or_hang() {
    let seeds = [
        card_png(&[("chara", &v2("Maren"))]),
        card_png(&[("chara", &v2("Maren")), ("ccv3", &v3("Maren"))]),
        png::with_text_chunks(&tiny_png(), &[], &[("chara", &v2("Raw").to_string())]).unwrap(),
    ];
    let mut rng = XorShift(0x5a6e_c0de_2026_0916);
    let started = Instant::now();
    let mut slowest = Duration::ZERO;
    for case in 0..20_000 {
        let mut bytes = seeds[case % seeds.len()].clone();
        for _ in 0..=rng.below(4) {
            let at = rng.below(bytes.len());
            match rng.below(7) {
                0 => bytes[at] ^= 1 << rng.below(8),
                1 => bytes[at] = rng.next() as u8,
                2 => bytes.truncate(at),
                // Overwrite what may be a length field with an extreme value.
                3 if at + 4 <= bytes.len() => {
                    let value =
                        [0u32, 1, 0x7fff_ffff, 0x8000_0000, 0xffff_fff8, u32::MAX][rng.below(6)];
                    bytes[at..at + 4].copy_from_slice(&value.to_be_bytes());
                }
                4 => {
                    let end = (at + rng.below(64)).min(bytes.len());
                    let copy = bytes[at..end].to_vec();
                    let to = rng.below(bytes.len());
                    bytes.splice(to..to, copy);
                }
                5 => {
                    let end = (at + rng.below(64)).min(bytes.len());
                    bytes.drain(at..end);
                }
                _ => bytes.insert(at, rng.next() as u8),
            }
            if bytes.is_empty() {
                break;
            }
        }
        let one = Instant::now();
        let _ = card::read_png(&bytes);
        slowest = slowest.max(one.elapsed());
    }
    assert!(
        slowest < Duration::from_millis(250),
        "one read took {slowest:?}"
    );
    assert!(started.elapsed() < Duration::from_secs(60));
}

#[test]
fn a_cut_off_file_still_yields_the_card_before_the_damage() {
    let mut png = card_png(&[("chara", &v2("Maren"))]);
    // Cut inside the image data, which comes after the card chunk.
    let idat = png.windows(4).position(|w| w == b"IDAT").unwrap();
    png.truncate(idat + 6);
    let report = card::read_png(&png);
    assert!(report.ok, "{report:#?}");
    assert_eq!(report.card.as_ref().unwrap().name, "Maren");
    assert_eq!(report.findings[0].severity, Severity::Warning);
    assert!(
        report.findings[0].message.contains("damaged"),
        "{report:#?}"
    );

    // Damage before the card leaves nothing to read.
    let mut early = card_png(&[("chara", &v2("Maren"))]);
    let text = early.windows(4).position(|w| w == b"tEXt").unwrap();
    early.truncate(text + 10);
    let report = card::read_png(&early);
    assert!(!report.ok);
    assert_eq!(
        report.findings[0].message,
        "no character card found in this PNG"
    );
}
