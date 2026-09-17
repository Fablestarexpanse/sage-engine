//! `sage export <world.db> <id>[@version] <out.png>`: an installed agent fragment as a SAGE
//! card.
//!
//! A SAGE card is the fragment's card PNG, unchanged, plus a `sage` chunk holding the fragment
//! manifest. The Tavern `chara` chunk the card already has stays, so SillyTavern, Chub and
//! CharacterBinder read it as before. Because the content digest covers the card without its
//! `sage` chunk, installing the exported card anywhere gives the same fragment, id, version and
//! digest, and installing it where the fragment already is reports `already-installed`.

use std::path::Path;

use sage_schema::card::{self, MAX_SAGE_CARD_BYTES, SAGE_KEYWORD};
use sage_schema::png;
use sage_schema::{Kind, digest::MANIFEST_FILE};

use crate::library::Installed;

pub fn run(world: &Path, spec: &str, out: &Path) -> Result<(), String> {
    let (id, version) = match spec.split_once('@') {
        Some((id, version)) => (id, Some(version)),
        None => (spec, None),
    };
    let installed = Installed::find(world, id, version)?;
    let manifest = &installed.manifest;
    let format = manifest.content.as_ref().map(|c| c.format.as_str());
    if manifest.kind != Kind::Agent || format != Some("png-card") {
        return Err(format!(
            "{id} is not a PNG agent card; only `png-card` agent fragments export as SAGE cards"
        ));
    }
    let original = installed
        .file("card.png")
        .ok_or("the installed fragment has no card.png")?;
    let text = std::str::from_utf8(installed.file(MANIFEST_FILE).ok_or("no manifest")?)
        .map_err(|_| "the manifest is not UTF-8")?;

    // The exported card must strip back to exactly these bytes, or its digest would differ.
    let canonical =
        png::with_text_chunks(original, &[SAGE_KEYWORD], &[]).map_err(|e| e.to_string())?;
    if canonical != original {
        return Err(format!(
            "{id}'s card.png is not in canonical form; install it again from the card file"
        ));
    }

    let chunk = card::sage_chunk(text);
    let (texts, _) = png::text_chunks(original).map_err(|e| e.to_string())?;
    let card_bytes: usize = texts
        .iter()
        .filter(|t| card::CARD_KEYWORDS.contains(&t.keyword.as_str()))
        .filter_map(|t| t.text.map(<[u8]>::len))
        .sum::<usize>()
        + chunk.len();
    if card_bytes > MAX_SAGE_CARD_BYTES {
        return Err(format!(
            "the card data is {card_bytes} bytes; a SAGE card holds at most 1 MiB, so share this one with `sage pack`"
        ));
    }
    let tavern = texts.iter().any(|t| t.keyword == "chara");

    let exported = png::with_text_chunks(original, &[SAGE_KEYWORD], &[(SAGE_KEYWORD, &chunk)])
        .map_err(|e| e.to_string())?;
    // Check the round trip before writing anything.
    let stripped =
        png::with_text_chunks(&exported, &[SAGE_KEYWORD], &[]).map_err(|e| e.to_string())?;
    if stripped != original || card::sage_manifest(&exported) != Some(Ok(text.to_owned())) {
        return Err("the exported card did not read back as this fragment".into());
    }
    std::fs::write(out, &exported).map_err(|e| format!("{}: {e}", out.display()))?;

    let mut warnings = Vec::new();
    if !tavern {
        warnings.push("the card has no `chara` chunk, so Tavern v2 tools will not read it");
    }
    let report = serde_json::json!({
        "ok": true,
        "fragment": manifest.id.as_str(),
        "version": manifest.version,
        "digest": installed.digest,
        "path": out.display().to_string(),
        "bytes": exported.len(),
        "tavern_compatible": tavern,
        "warnings": warnings,
    });
    println!("{report}");
    Ok(())
}
