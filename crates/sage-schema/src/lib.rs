//! Fragment manifests: types and validation.
//!
//! This crate is the single definition of what a valid `fragment.yaml` is. The engine, `sage
//! check`, and Fragment Foundry all run this code (the Foundry through its WASM build), so they
//! cannot disagree about a manifest.
//!
//! Validation never stops at the first problem: it reports every problem it can find, each with
//! a path such as `requires[1].version`, in a stable order.

pub mod card;
mod manifest;
pub mod png;
mod rules;

pub use manifest::{
    Content, Creator, Dependency, Derivation, FragmentId, Integrity, Kind, Manifest, Provides,
};

use serde::Serialize;

/// Manifest format this crate reads and writes.
pub const MANIFEST_SCHEMA: &str = "sage.fragment/1";

/// Largest manifest accepted, in bytes. A manifest is metadata; anything bigger is a mistake
/// or an attack.
pub const MAX_MANIFEST_BYTES: usize = 64 * 1024;

/// One thing wrong with a manifest.
#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
pub struct Problem {
    /// Where, e.g. `requires[1].version`. Empty for the document as a whole.
    pub path: String,
    /// What is wrong, in plain words.
    pub message: String,
}

/// The result of validating a manifest.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Report {
    /// Whether the manifest has no problems.
    pub valid: bool,
    /// Every problem found, in document order.
    pub problems: Vec<Problem>,
    /// The manifest in normalized form, present only when valid.
    pub manifest: Option<Manifest>,
}

impl Report {
    /// The report as compact JSON. Byte-identical between native and WASM builds.
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("reports serialize")
    }
}

/// Validates the text of a `fragment.yaml`.
pub fn validate_manifest(text: &str) -> Report {
    let problems_only = |problem: Problem| Report {
        valid: false,
        problems: vec![problem],
        manifest: None,
    };
    if text.len() > MAX_MANIFEST_BYTES {
        return problems_only(Problem {
            path: String::new(),
            message: format!(
                "manifest is {} bytes; the limit is {MAX_MANIFEST_BYTES}",
                text.len()
            ),
        });
    }
    let raw = match serde_saphyr::from_str::<manifest::RawManifest>(text) {
        Ok(raw) => raw,
        Err(error) => {
            let first_line = error.to_string();
            let first_line = first_line.lines().next().unwrap_or_default();
            return problems_only(Problem {
                path: String::new(),
                message: first_line
                    .strip_prefix("error: ")
                    .unwrap_or(first_line)
                    .to_owned(),
            });
        }
    };
    match rules::check(raw) {
        Ok(manifest) => Report {
            valid: true,
            problems: Vec::new(),
            manifest: Some(manifest),
        },
        Err(problems) => Report {
            valid: false,
            problems,
            manifest: None,
        },
    }
}
