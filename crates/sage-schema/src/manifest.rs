//! Manifest shapes: the raw form as written, and the validated form everything else uses.

use serde::{Deserialize, Serialize};

// ---- As written. Everything is a string so validation can explain problems itself. ----

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawManifest {
    pub schema: String,
    pub id: String,
    pub kind: String,
    pub version: String,
    pub engine: String,
    pub title: String,
    #[serde(default)]
    pub description: Option<String>,
    pub creator: RawCreator,
    pub license: String,
    #[serde(default)]
    pub derived_from: Vec<RawDerivation>,
    #[serde(default)]
    pub requires: Vec<RawDependency>,
    #[serde(default)]
    pub provides: RawProvides,
    #[serde(default)]
    pub capabilities: Option<Vec<String>>,
    #[serde(default)]
    pub content: Option<RawContent>,
    #[serde(default)]
    pub integrity: Option<RawIntegrity>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawCreator {
    pub handle: String,
    #[serde(default)]
    pub foundry_id: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawDerivation {
    pub id: String,
    pub version: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawDependency {
    pub id: String,
    pub version: String,
    #[serde(default)]
    pub optional: bool,
}

#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawProvides {
    #[serde(default)]
    pub commands: Vec<String>,
    #[serde(default)]
    pub panels: Vec<String>,
    #[serde(default)]
    pub components: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawContent {
    pub format: String,
    #[serde(default)]
    pub tavern_compatible: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawIntegrity {
    pub digest: String,
    #[serde(default)]
    pub signature: Option<String>,
}

// ---- Validated. ----

/// A fragment id: `creator.slug`, lowercase letters, digits and inner hyphens.
#[derive(Serialize, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[serde(transparent)]
pub struct FragmentId(pub(crate) String);

impl FragmentId {
    /// The creator part, before the dot.
    pub fn creator(&self) -> &str {
        self.0.split_once('.').map(|(c, _)| c).unwrap_or_default()
    }

    /// The slug part, after the dot.
    pub fn slug(&self) -> &str {
        self.0.split_once('.').map(|(_, s)| s).unwrap_or_default()
    }

    /// The whole id.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// What a fragment is.
#[derive(Serialize, Clone, Copy, Debug, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    /// A synthetic agent.
    Agent,
    /// A place in the space graph.
    Place,
    /// A group of places.
    Zone,
    /// A thing.
    Item,
    /// A quest.
    Quest,
    /// Lore entries.
    Lorebook,
    /// Rules expressed as configuration.
    Ruleset,
    /// A whole world.
    World,
    /// A code fragment: a WASM component.
    Plugin,
}

impl Kind {
    pub(crate) const ALL: [(&'static str, Kind); 9] = [
        ("agent", Kind::Agent),
        ("place", Kind::Place),
        ("zone", Kind::Zone),
        ("item", Kind::Item),
        ("quest", Kind::Quest),
        ("lorebook", Kind::Lorebook),
        ("ruleset", Kind::Ruleset),
        ("world", Kind::World),
        ("plugin", Kind::Plugin),
    ];
}

/// Who made the fragment.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Creator {
    /// Handle; always equals the id's creator part.
    pub handle: String,
    /// Foundry account id, set on publish.
    pub foundry_id: Option<String>,
}

/// A fragment this one was remixed from.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Derivation {
    /// Source fragment.
    pub id: FragmentId,
    /// Exact source version.
    pub version: String,
}

/// A fragment this one needs.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Dependency {
    /// Required fragment.
    pub id: FragmentId,
    /// Accepted versions, Cargo-style (`^1.2`, `>=0.3, <0.5`).
    pub version: String,
    /// Whether the fragment works without it.
    pub optional: bool,
}

/// What the fragment adds, for sites, clients and editors to render.
#[derive(Serialize, Clone, Debug, PartialEq, Default)]
pub struct Provides {
    /// Player commands.
    pub commands: Vec<String>,
    /// Client panels.
    pub panels: Vec<String>,
    /// Component names, each prefixed with the fragment id.
    pub components: Vec<String>,
}

/// How a content fragment's data is packaged.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Content {
    /// `png-card`, `yaml` or `json`.
    pub format: String,
    /// Whether an agent card also carries a Tavern v2 `chara` chunk.
    pub tavern_compatible: bool,
}

/// Digest and signature of the published package.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Integrity {
    /// `sha256:` followed by 64 lowercase hex digits.
    pub digest: String,
    /// Signature, format checked at M4 when signing lands.
    pub signature: Option<String>,
}

/// A valid manifest.
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Manifest {
    /// Always [`crate::MANIFEST_SCHEMA`].
    pub schema: String,
    /// Fragment id.
    pub id: FragmentId,
    /// Fragment kind.
    pub kind: Kind,
    /// Semver version.
    pub version: String,
    /// Engine versions this fragment works with, Cargo-style requirement.
    pub engine: String,
    /// Display title.
    pub title: String,
    /// Longer description.
    pub description: Option<String>,
    /// Creator.
    pub creator: Creator,
    /// SPDX license expression; `LicenseRef-*` allowed.
    pub license: String,
    /// Remix sources.
    pub derived_from: Vec<Derivation>,
    /// Dependencies.
    pub requires: Vec<Dependency>,
    /// What it adds.
    pub provides: Provides,
    /// Plugins only: WIT interfaces it imports, e.g. `sage:core/entities@0.1.0`.
    pub capabilities: Option<Vec<String>>,
    /// Content fragments only: packaging.
    pub content: Option<Content>,
    /// Package integrity.
    pub integrity: Option<Integrity>,
}

impl Manifest {
    /// The engine requirement, parsed.
    pub fn engine_requirement(&self) -> semver::VersionReq {
        semver::VersionReq::parse(&self.engine).expect("validated")
    }
}
