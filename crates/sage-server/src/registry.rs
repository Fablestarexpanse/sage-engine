//! A static fragment registry: `sage registry build` writes it, `sage install --registry`
//! reads it.
//!
//! The Foundry's read path is plain files, so any static host serves it:
//!
//! - `index.json`: every fragment and version (`sage.registry/1`), and every input refused
//! - `api/v1/fragments/<id>.json`: one fragment's entry, what `sage install` fetches
//! - `blobs/sha256/<hex>.sagepkg` or `.png`: the files, named by the sha256 of each file
//!
//! Building runs exactly the checks `sage install` runs, so the site can only list what the
//! engine would install. The output has no timestamps and a stable order: the same inputs
//! build the same registry.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use sage_schema::{Kind, Manifest};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::Digest as _;

use crate::check::ENGINE_VERSION;
use crate::library::{self, CardOptions, InstallReport, Verified};

/// Format of `index.json` and the per-fragment files.
pub const REGISTRY_SCHEMA: &str = "sage.registry/1";

/// One version of a fragment, as the registry lists it.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct VersionEntry {
    /// Exact version.
    pub version: String,
    /// Engine requirement from the manifest.
    pub engine: String,
    /// Content digest; `sage install` pins it.
    pub digest: String,
    /// Where the file is, relative to the registry root.
    pub url: String,
    /// `sagepkg` or `sage-card`.
    pub format: String,
    /// File size in bytes.
    pub bytes: u64,
    /// The manifest, normalized.
    pub manifest: Value,
    /// For agents: what the card becomes, for the fragment page.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent: Option<Value>,
    /// What installing it reports, for the fragment page.
    #[serde(default)]
    pub warnings: Vec<String>,
}

/// A fragment and all its versions, newest first.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct FragmentEntry {
    /// Schema of this file.
    pub schema: String,
    /// `creator.slug`.
    pub id: String,
    /// Kind, from the newest version.
    pub kind: String,
    /// Title, from the newest version.
    pub title: String,
    /// Newest version.
    pub latest: String,
    /// Every version, newest first.
    pub versions: Vec<VersionEntry>,
}

/// A version accepted for listing: parsed version, entry, file bytes, file extension.
type Listed = (semver::Version, VersionEntry, Vec<u8>, &'static str);

#[derive(Serialize)]
struct Refused {
    source: String,
    problems: Vec<String>,
}

#[derive(Serialize)]
struct Index<'a> {
    schema: &'static str,
    built_by: String,
    fragments: Vec<&'a FragmentEntry>,
    refused: Vec<Refused>,
}

/// `sage registry build <inputs-dir> <out-dir>`: every `.sagepkg`, SAGE card PNG and fragment
/// directory directly inside `inputs-dir` becomes part of the registry in `out-dir`.
pub fn build(inputs: &Path, out: &Path) -> Result<(), String> {
    // The output is replaced wholesale, so refuse anything that is not already a registry.
    if out.exists() && !is_registry_or_empty(out) {
        return Err(format!(
            "{} exists and is not a registry built by sage; choose an empty or new directory",
            out.display()
        ));
    }
    // An output that does not exist yet is judged by where it would be created.
    let resolve = |p: &Path| {
        p.canonicalize().ok().or_else(|| {
            let parent = p
                .parent()
                .filter(|d| !d.as_os_str().is_empty())
                .unwrap_or(Path::new("."));
            Some(parent.canonicalize().ok()?.join(p.file_name()?))
        })
    };
    let nested = match (resolve(inputs), resolve(out)) {
        (Some(a), Some(b)) => a.starts_with(&b) || b.starts_with(&a),
        _ => false,
    };
    if nested {
        return Err("the inputs and output directories must not contain each other".into());
    }
    let mut sources: Vec<PathBuf> = std::fs::read_dir(inputs)
        .map_err(|e| format!("{}: {e}", inputs.display()))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or_default();
            !name.starts_with('.')
        })
        .collect();
    sources.sort();

    let mut refused = Vec::new();
    let mut by_id: BTreeMap<String, Vec<Listed>> = BTreeMap::new();
    for source in &sources {
        let label = source
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default()
            .to_owned();
        match entry_for(source) {
            Ok((entry, id, blob, extension)) => {
                let version = semver::Version::parse(&entry.version).expect("validated");
                let versions = by_id.entry(id.clone()).or_default();
                match versions.iter().find(|(v, ..)| *v == version) {
                    Some((_, existing, ..)) if existing.digest == entry.digest => {}
                    Some((_, existing, ..)) => refused.push(Refused {
                        source: label,
                        problems: vec![format!(
                            "{id}@{} is already listed with different content ({})",
                            entry.version, existing.digest
                        )],
                    }),
                    None => versions.push((version, entry, blob, extension)),
                }
            }
            Err(problems) => refused.push(Refused {
                source: label,
                problems,
            }),
        }
    }

    // Write into a fresh directory, then swap, so a failed build never leaves half a registry.
    let staging = out.with_extension("building");
    let _ = std::fs::remove_dir_all(&staging);
    std::fs::create_dir_all(staging.join("blobs/sha256"))
        .and_then(|()| std::fs::create_dir_all(staging.join("api/v1/fragments")))
        .map_err(|e| format!("{}: {e}", staging.display()))?;
    let write = |path: PathBuf, bytes: &[u8]| {
        std::fs::write(&path, bytes).map_err(|e| format!("{}: {e}", path.display()))
    };

    let mut fragments = Vec::new();
    for (id, mut versions) in by_id {
        versions.sort_by(|a, b| b.0.cmp(&a.0));
        for (_, entry, blob, _) in &versions {
            write(staging.join(&entry.url), blob)?;
        }
        let newest = &versions[0].1;
        let entry = FragmentEntry {
            schema: REGISTRY_SCHEMA.into(),
            id: id.clone(),
            kind: newest.manifest["kind"]
                .as_str()
                .unwrap_or_default()
                .to_owned(),
            title: newest.manifest["title"]
                .as_str()
                .unwrap_or_default()
                .to_owned(),
            latest: newest.version.clone(),
            versions: versions.into_iter().map(|(_, e, ..)| e).collect(),
        };
        write(
            staging.join(format!("api/v1/fragments/{id}.json")),
            &pretty(&entry),
        )?;
        fragments.push(entry);
    }
    let index = Index {
        schema: REGISTRY_SCHEMA,
        built_by: format!("sage {ENGINE_VERSION}"),
        fragments: fragments.iter().collect(),
        refused,
    };
    write(staging.join("index.json"), &pretty(&index))?;

    if out.exists() {
        std::fs::remove_dir_all(out).map_err(|e| format!("{}: {e}", out.display()))?;
    }
    std::fs::rename(&staging, out).map_err(|e| format!("{}: {e}", out.display()))?;

    let summary = serde_json::json!({
        "ok": index.refused.is_empty(),
        "fragments": fragments.len(),
        "versions": fragments.iter().map(|f| f.versions.len()).sum::<usize>(),
        "refused": index.refused,
        "path": out.display().to_string(),
    });
    println!("{summary}");
    if index.refused.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "{} input(s) refused; the registry lists only the rest",
            index.refused.len()
        ))
    }
}

fn is_registry_or_empty(dir: &Path) -> bool {
    let Ok(mut entries) = std::fs::read_dir(dir) else {
        return false;
    };
    if entries.next().is_none() {
        return true;
    }
    std::fs::read(dir.join("index.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
        .is_some_and(|index| index["schema"] == REGISTRY_SCHEMA)
}

fn pretty<T: Serialize>(value: &T) -> Vec<u8> {
    let mut text = serde_json::to_vec_pretty(value).expect("registry JSON serializes");
    text.push(b'\n');
    text
}

/// Verifies one input and describes it. Returns the entry, the id, the blob and its extension.
fn entry_for(source: &Path) -> Result<(VersionEntry, String, Vec<u8>, &'static str), Vec<String>> {
    let (verified, blob, format, extension) = if source.is_dir() {
        let verified = library::verify(source, None, &CardOptions::default(), false)?;
        let blob = crate::package::pack(&verified.files).map_err(|e| vec![e])?;
        (verified, blob, "sagepkg", "sagepkg")
    } else {
        let bytes =
            std::fs::read(source).map_err(|e| vec![format!("{}: {e}", source.display())])?;
        if bytes.starts_with(&crate::package::ZSTD_MAGIC) {
            let verified = library::verify(
                Path::new("input.sagepkg"),
                Some(bytes.clone()),
                &CardOptions::default(),
                false,
            )?;
            (verified, bytes, "sagepkg", "sagepkg")
        } else if bytes.starts_with(&sage_schema::png::SIGNATURE) {
            if sage_schema::card::sage_manifest(&bytes).is_none() {
                return Err(vec![
                    "a plain character card has no manifest; export it as a SAGE card or pack it as a fragment first".into(),
                ]);
            }
            let verified = library::verify(
                Path::new("input.png"),
                Some(bytes.clone()),
                &CardOptions::default(),
                false,
            )?;
            (verified, bytes, "sage-card", "png")
        } else {
            return Err(vec![
                "not a .sagepkg, a SAGE card or a fragment directory".into(),
            ]);
        }
    };
    let Verified {
        manifest,
        digest,
        files,
        warnings,
    } = verified;
    // Files are named by the sha256 of the file itself: two fragments can share content (the
    // content digest leaves out the manifest) but never a file.
    let hex: String = sha2::Sha256::digest(&blob)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    let agent = (manifest.kind == Kind::Agent)
        .then(|| library::agent_of(&manifest, &files).ok())
        .flatten()
        .map(|agent| serde_json::to_value(agent).expect("agents serialize"));
    let entry = VersionEntry {
        version: manifest.version.clone(),
        engine: manifest.engine.clone(),
        digest: digest.clone(),
        url: format!("blobs/sha256/{hex}.{extension}"),
        format: format.into(),
        bytes: blob.len() as u64,
        manifest: serde_json::to_value(&manifest).expect("manifests serialize"),
        agent,
        warnings: warnings
            .into_iter()
            .filter(|w| !w.starts_with("unsigned"))
            .collect(),
    };
    Ok((entry, manifest.id.as_str().to_owned(), blob, extension))
}

/// Installs `spec` (`id` or `id@requirement`) from the registry at `base`: the newest version
/// matching the requirement whose engine range accepts this engine, pinned to its digest.
pub fn install(world: &Path, spec: &str, base: &str) -> InstallReport {
    let refuse = |problem: String| library::install_verified(world, Err(vec![problem]));
    let (id, requirement) = match spec.split_once('@') {
        Some((id, req)) => (id, req),
        None => (spec, "*"),
    };
    if !library::safe_name(id) || !id.contains('.') {
        return refuse(format!("`{id}` is not a fragment id"));
    }
    let requirement = match semver::VersionReq::parse(requirement) {
        Ok(requirement) => requirement,
        Err(e) => return refuse(format!("`{requirement}` is not a version requirement: {e}")),
    };
    let base = base.trim_end_matches('/');
    let listing_url = format!("{base}/api/v1/fragments/{id}.json");
    let listing = match crate::download::fetch(&listing_url) {
        Ok((_, bytes)) => bytes,
        Err(e) if e.contains("404") => {
            return refuse(format!("{id} is not in the registry at {base}"));
        }
        Err(e) => return refuse(e),
    };
    let entry: FragmentEntry = match serde_json::from_slice(&listing) {
        Ok(entry) => entry,
        Err(e) => return refuse(format!("{listing_url} is not a registry entry: {e}")),
    };
    if entry.schema != REGISTRY_SCHEMA || entry.id != id {
        return refuse(format!("{listing_url} does not describe {id}"));
    }
    let engine = semver::Version::parse(ENGINE_VERSION).expect("engine version is semver");
    let chosen = entry
        .versions
        .iter()
        .filter_map(|v| {
            semver::Version::parse(&v.version)
                .ok()
                .map(|parsed| (parsed, v))
        })
        .filter(|(parsed, v)| {
            requirement.matches(parsed)
                && semver::VersionReq::parse(&v.engine).is_ok_and(|r| r.matches(&engine))
        })
        .max_by(|a, b| a.0.cmp(&b.0))
        .map(|(_, v)| v.clone());
    let Some(chosen) = chosen else {
        let listed: Vec<String> = entry
            .versions
            .iter()
            .map(|v| format!("{} (engine {})", v.version, v.engine))
            .collect();
        return refuse(format!(
            "no version of {id} matches `{requirement}` and engine {ENGINE_VERSION}; listed: {}",
            listed.join(", ")
        ));
    };
    if chosen.url.contains("..") || chosen.url.starts_with('/') || chosen.url.contains("://") {
        return refuse(format!(
            "{listing_url} points outside the registry: {}",
            chosen.url
        ));
    }
    let blob_url = format!("{base}/{}", chosen.url);
    let verified = crate::download::fetch(&blob_url)
        .map_err(|e| vec![e])
        .and_then(|(name, bytes)| {
            library::verify(&name, Some(bytes), &CardOptions::default(), true)
        })
        .and_then(|verified| {
            check_is(&verified.manifest, &verified.digest, id, &chosen).map(|()| verified)
        });
    let mut report = library::install_verified(world, verified);
    report.set_source(format!("{id}@{} from {base}", chosen.version));
    report
}

/// The registry must deliver exactly what it listed.
fn check_is(
    manifest: &Manifest,
    digest: &str,
    id: &str,
    listed: &VersionEntry,
) -> Result<(), Vec<String>> {
    if manifest.id.as_str() != id || manifest.version != listed.version {
        return Err(vec![format!(
            "the registry listed {id}@{} but served {}@{}",
            listed.version,
            manifest.id.as_str(),
            manifest.version
        )]);
    }
    if digest != listed.digest {
        return Err(vec![format!(
            "the content is {digest}, not the {} the registry listed",
            listed.digest
        )]);
    }
    Ok(())
}
