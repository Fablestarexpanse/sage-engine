//! A world's fragment library, `<world>.fragments/`, and `sage install`.
//!
//! Installing verifies a fragment and copies it to `<world>.fragments/<id>/<version>/`. It
//! never touches the world itself: placing what a fragment contains is a separate, logged step
//! (`sage place`). An installed version is immutable. Installing the same content again is a
//! no-op; installing different content under the same id and version is refused.
//!
//! Integrity is the content digest (`sage_schema::digest`): a manifest that states one must
//! match, and one that does not gets it recorded. Nothing is signed yet (signatures arrive with
//! Foundry uploads), so every install says so.

use std::path::{Path, PathBuf};

use sage_agents::card::{ImportedAgent, agent_from_card};
use sage_schema::card::{self, Severity};
use sage_schema::digest::{MANIFEST_FILE, content_digest};
use sage_schema::{Kind, Manifest};
use serde::Serialize;

use crate::check::ENGINE_VERSION;

/// Most files in a fragment.
pub const MAX_FILES: usize = 256;

/// Largest fragment, all files together, in bytes.
pub const MAX_FRAGMENT_BYTES: u64 = 64 * 1024 * 1024;

/// The library directory for a world file.
pub fn library_path(world: &Path) -> PathBuf {
    let mut name = world.as_os_str().to_owned();
    name.push(".fragments");
    PathBuf::from(name)
}

/// A fragment's files, read into memory: `/`-separated relative paths and bytes.
pub struct Files(pub Vec<(String, Vec<u8>)>);

impl Files {
    pub(crate) fn get(&self, path: &str) -> Option<&[u8]> {
        self.0
            .iter()
            .find(|(p, _)| p == path)
            .map(|(_, b)| b.as_slice())
    }

    fn digest(&self) -> Result<String, String> {
        let borrowed: Vec<(&str, &[u8])> = self
            .0
            .iter()
            .map(|(p, b)| (p.as_str(), b.as_slice()))
            .collect();
        content_digest(&borrowed)
    }

    /// Reads a fragment directory. Refuses links, unusual file names, and anything over the
    /// file-count and size limits.
    pub fn read_dir(root: &Path) -> Result<Files, String> {
        let mut files = Vec::new();
        let mut total = 0u64;
        let mut pending = vec![(root.to_path_buf(), String::new())];
        while let Some((dir, prefix)) = pending.pop() {
            let entries = std::fs::read_dir(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
            for entry in entries {
                let entry = entry.map_err(|e| format!("{}: {e}", dir.display()))?;
                let name = entry.file_name();
                let name = name
                    .to_str()
                    .filter(|n| safe_name(n))
                    .ok_or_else(|| {
                        format!(
                            "{}: file names may use only letters, digits, `.`, `_`, `-` and `+`",
                            entry.path().display()
                        )
                    })?
                    .to_owned();
                let path = if prefix.is_empty() {
                    name
                } else {
                    format!("{prefix}/{name}")
                };
                let kind = entry
                    .path()
                    .symlink_metadata()
                    .map_err(|e| format!("{}: {e}", entry.path().display()))?;
                if kind.file_type().is_symlink() {
                    return Err(format!("{path}: links are not allowed in a fragment"));
                } else if kind.is_dir() {
                    pending.push((entry.path(), path));
                } else {
                    total += kind.len();
                    if files.len() == MAX_FILES || total > MAX_FRAGMENT_BYTES {
                        return Err(format!(
                            "a fragment has at most {MAX_FILES} files and {} MiB",
                            MAX_FRAGMENT_BYTES / (1024 * 1024)
                        ));
                    }
                    let bytes = std::fs::read(entry.path())
                        .map_err(|e| format!("{}: {e}", entry.path().display()))?;
                    files.push((path, bytes));
                }
            }
        }
        files.sort();
        Ok(Files(files))
    }

    pub(crate) fn write_to(&self, dir: &Path) -> Result<(), String> {
        for (path, bytes) in &self.0 {
            let target = dir.join(path);
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| format!("{}: {e}", parent.display()))?;
            }
            std::fs::write(&target, bytes).map_err(|e| format!("{}: {e}", target.display()))?;
        }
        Ok(())
    }
}

pub(crate) fn safe_name(name: &str) -> bool {
    !name.is_empty()
        && name != "."
        && name != ".."
        && name.len() <= 128
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-' | b'+'))
}

/// What `sage install` reports, as one line of JSON.
#[derive(Serialize, Default)]
pub struct InstallReport {
    /// Whether the fragment is installed now (freshly or already).
    pub ok: bool,
    /// `installed` or `already-installed`, when ok.
    pub status: Option<&'static str>,
    /// What was named on the command line: a path or a URL.
    source: Option<String>,
    fragment: Option<String>,
    version: Option<String>,
    kind: Option<Kind>,
    digest: Option<String>,
    path: Option<String>,
    /// Why it was not installed.
    problems: Vec<String>,
    /// Installed, but worth knowing.
    warnings: Vec<String>,
}

/// Overrides for a card installed straight from a PNG or JSON file.
#[derive(Default, Debug, PartialEq)]
pub struct CardOptions {
    /// Fragment id; default `local.<name as a slug>`.
    pub id: Option<String>,
    /// Version; default the card's own version if it is semver, else `0.1.0`.
    pub version: Option<String>,
    /// SPDX license; default `LicenseRef-Unspecified`.
    pub license: Option<String>,
}

/// A fragment that passed every check, ready to install or pack.
pub struct Verified {
    /// Its manifest.
    pub manifest: Manifest,
    /// Its content digest, equal to the one in the stored manifest.
    pub digest: String,
    /// Every file, with `fragment.yaml` as it is stored: always stating the digest.
    pub files: Files,
    /// Accepted, but worth knowing.
    pub warnings: Vec<String>,
}

/// Whether `source` is a `.sagepkg` package: by extension, or by the zstd frame magic.
fn is_package(source: &Path, bytes: &[u8]) -> bool {
    source
        .extension()
        .is_some_and(|e| e.eq_ignore_ascii_case("sagepkg"))
        || bytes.starts_with(&crate::package::ZSTD_MAGIC)
}

fn manifest_text(files: &Files) -> Result<String, String> {
    let text = files
        .get(MANIFEST_FILE)
        .ok_or_else(|| format!("no {MANIFEST_FILE}"))?;
    String::from_utf8(text.to_vec()).map_err(|_| format!("{MANIFEST_FILE} is not UTF-8"))
}

/// Reads and checks a fragment directory, a `.sagepkg` package, or a card file. `engine`
/// also requires the manifest's engine range to accept this engine (install does; packing
/// for another engine is allowed).
///
/// With `downloaded`, the bytes are the source and `source` is only its file name, used to
/// tell a package or card by extension and in messages.
pub fn verify(
    source: &Path,
    downloaded: Option<Vec<u8>>,
    options: &CardOptions,
    engine: bool,
) -> Result<Verified, Vec<String>> {
    let local_dir = downloaded.is_none() && source.is_dir();
    let mut warnings = Vec::new();
    let only_cards = |what: &str| {
        if *options != CardOptions::default() {
            Err(vec![format!(
                "--id, --version and --license apply only to plain card files, not {what}"
            )])
        } else {
            Ok(())
        }
    };
    let (mut files, mut text) = if local_dir {
        only_cards("fragment directories")?;
        let files = Files::read_dir(source).map_err(|e| vec![e])?;
        let text = manifest_text(&files).map_err(|e| vec![format!("{}: {e}", source.display())])?;
        (files, text)
    } else {
        let bytes = match downloaded {
            Some(bytes) => bytes,
            None => read_limited(source).map_err(|e| vec![e])?,
        };
        if is_package(source, &bytes) {
            only_cards("packages")?;
            let files = crate::package::unpack(&bytes)
                .map_err(|e| vec![format!("{}: {e}", source.display())])?;
            let text =
                manifest_text(&files).map_err(|e| vec![format!("{}: {e}", source.display())])?;
            (files, text)
        } else {
            card_fragment(source, &bytes, options, &mut warnings).map_err(|e| vec![e])?
        }
    };

    let manifest = valid_manifest(&text)?;
    if engine {
        let this = semver::Version::parse(ENGINE_VERSION).expect("engine version is semver");
        if !manifest.engine_requirement().matches(&this) {
            return Err(vec![format!(
                "needs engine `{}`; this is {ENGINE_VERSION}",
                manifest.engine
            )]);
        }
    }

    let digest = files.digest().map_err(|e| vec![e])?;
    match &manifest.integrity {
        Some(integrity) if integrity.digest != digest => {
            return Err(vec![format!(
                "content does not match its manifest: the manifest says {}, the files are {digest}",
                integrity.digest
            )]);
        }
        Some(integrity) if integrity.signature.is_some() => warnings.push(
            "the signature was not checked: this engine does not verify signatures yet".into(),
        ),
        Some(_) => warnings.push("unsigned: accepted on its content digest alone".into()),
        None => {
            warnings.push(format!(
                "unsigned, and the manifest stated no digest: recorded {digest}"
            ));
            if !text.ends_with('\n') {
                text.push('\n');
            }
            text.push_str(&format!("integrity:\n  digest: \"{digest}\"\n"));
        }
    }

    match manifest.kind {
        Kind::Agent => {
            let (_, card_warnings) = usable_agent(&manifest, &files)?;
            warnings.extend(card_warnings);
        }
        Kind::Plugin => plugin_checks(local_dir.then_some(source), &files)?,
        other => {
            return Err(vec![format!(
                "`{}` fragments cannot be installed yet",
                serde_json::to_value(other)
                    .ok()
                    .and_then(|v| v.as_str().map(str::to_owned))
                    .unwrap_or_default()
            )]);
        }
    }

    files.0.retain(|(path, _)| path != MANIFEST_FILE);
    files.0.push((MANIFEST_FILE.into(), text.into_bytes()));
    files.0.sort();
    Ok(Verified {
        manifest,
        digest,
        files,
        warnings,
    })
}

/// Reads a file of at most [`MAX_FRAGMENT_BYTES`].
fn read_limited(path: &Path) -> Result<Vec<u8>, String> {
    use std::io::Read;
    let file = std::fs::File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut bytes = Vec::new();
    file.take(MAX_FRAGMENT_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    if bytes.len() as u64 > MAX_FRAGMENT_BYTES {
        return Err(format!(
            "{}: over {} MiB",
            path.display(),
            MAX_FRAGMENT_BYTES / (1024 * 1024)
        ));
    }
    Ok(bytes)
}

impl InstallReport {
    /// Records what was installed from, as the user named it.
    pub fn set_source(&mut self, source: String) {
        self.source = Some(source);
    }
}

/// Installs what [`verify`] accepted, or reports why not.
pub fn install_verified(world: &Path, verified: Result<Verified, Vec<String>>) -> InstallReport {
    let mut report = InstallReport::default();
    let verified = match verified {
        Ok(verified) => verified,
        Err(problems) => {
            report.problems = problems;
            return report;
        }
    };
    let Verified {
        manifest,
        digest,
        files,
        warnings,
    } = verified;
    report.fragment = Some(manifest.id.as_str().to_owned());
    report.version = Some(manifest.version.clone());
    report.kind = Some(manifest.kind);
    report.digest = Some(digest.clone());
    report.warnings = warnings;

    let target = library_path(world)
        .join(manifest.id.as_str())
        .join(&manifest.version);
    report.path = Some(target.display().to_string());
    if target.exists() {
        match Installed::open(&target) {
            Ok(existing) if existing.digest == digest => {
                report.ok = true;
                report.status = Some("already-installed");
            }
            Ok(existing) => report.problems.push(format!(
                "{}@{} is already installed with different content ({}); give this one a new version",
                manifest.id.as_str(),
                manifest.version,
                existing.digest
            )),
            Err(problem) => report.problems.push(format!(
                "{}@{} is already installed but damaged: {problem}",
                manifest.id.as_str(),
                manifest.version
            )),
        }
        return report;
    }

    match write_atomically(&target, &files) {
        Ok(()) => {
            report.ok = true;
            report.status = Some("installed");
        }
        Err(problem) => report.problems.push(problem),
    }
    report
}

/// Writes into a temporary sibling, then renames, so a crash never leaves a half-installed
/// version where `sage place` would find it.
fn write_atomically(target: &Path, files: &Files) -> Result<(), String> {
    let parent = target.parent().expect("target has a parent");
    std::fs::create_dir_all(parent).map_err(|e| format!("{}: {e}", parent.display()))?;
    let temp = parent.join(format!(
        ".installing-{}-{}",
        target.file_name().and_then(|n| n.to_str()).unwrap_or("x"),
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&temp);
    let result = files.write_to(&temp).and_then(|()| {
        std::fs::rename(&temp, target).map_err(|e| format!("{}: {e}", target.display()))
    });
    if result.is_err() {
        let _ = std::fs::remove_dir_all(&temp);
    }
    result
}

fn valid_manifest(text: &str) -> Result<Manifest, Vec<String>> {
    let validation = sage_schema::validate_manifest(text);
    validation.manifest.ok_or_else(|| {
        validation
            .problems
            .iter()
            .map(|p| {
                if p.path.is_empty() {
                    format!("{MANIFEST_FILE}: {}", p.message)
                } else {
                    format!("{MANIFEST_FILE}: {}: {}", p.path, p.message)
                }
            })
            .collect()
    })
}

/// The card file an agent fragment's content format names.
fn card_file(manifest: &Manifest) -> Result<&'static str, String> {
    match manifest.content.as_ref().map(|c| c.format.as_str()) {
        Some("png-card") => Ok("card.png"),
        Some("json") => Ok("card.json"),
        Some(other) => Err(format!(
            "agent fragments hold a `png-card` or `json` card, not `{other}`"
        )),
        None => Err("an agent fragment needs a `content` section".into()),
    }
}

/// The agent an agent fragment holds, and warnings from reading and converting its card.
/// The agent an agent fragment's files hold.
pub(crate) fn agent_of(manifest: &Manifest, files: &Files) -> Result<ImportedAgent, Vec<String>> {
    usable_agent(manifest, files).map(|(agent, _)| agent)
}

fn usable_agent(
    manifest: &Manifest,
    files: &Files,
) -> Result<(ImportedAgent, Vec<String>), Vec<String>> {
    let file = card_file(manifest).map_err(|p| vec![p])?;
    let bytes = files
        .get(file)
        .ok_or_else(|| vec![format!("the fragment has no {file}")])?;
    let read = if file.ends_with(".png") {
        card::read_png(bytes)
    } else {
        card::read_json(bytes)
    };
    let mut findings = read.findings;
    let Some(card) = read.card.filter(|_| read.ok) else {
        return Err(findings
            .iter()
            .filter(|f| f.severity == Severity::Error)
            .map(|f| format!("{file}: {}", f.message))
            .collect());
    };
    let (agent, converted) = agent_from_card(&card);
    findings.extend(converted);
    let errors: Vec<String> = findings
        .iter()
        .filter(|f| f.severity == Severity::Error)
        .map(|f| format!("{file}: {}", f.message))
        .collect();
    if !errors.is_empty() {
        return Err(errors);
    }
    let warnings = findings
        .iter()
        .filter(|f| f.severity == Severity::Warning)
        .map(|f| {
            if f.path.is_empty() {
                format!("{file}: {}", f.message)
            } else {
                format!("{file}: {}: {}", f.path, f.message)
            }
        })
        .collect();
    Ok((agent, warnings))
}

/// Plugins are accepted only if `sage check` passes. A package is unpacked to a temporary
/// directory first, so it is checked exactly as a directory would be.
fn plugin_checks(dir: Option<&Path>, files: &Files) -> Result<(), Vec<String>> {
    if files.get("plugin.wasm").is_none() {
        return Err(vec!["a plugin fragment needs plugin.wasm".into()]);
    }
    let unpacked;
    let dir = if let Some(dir) = dir {
        dir
    } else {
        unpacked = tempfile::tempdir().map_err(|e| vec![e.to_string()])?;
        files.write_to(unpacked.path()).map_err(|e| vec![e])?;
        unpacked.path()
    };
    let report = crate::check::check(dir);
    if report.ok {
        return Ok(());
    }
    let value = serde_json::to_value(&report).expect("reports serialize");
    Err(value["checks"]
        .as_array()
        .into_iter()
        .flatten()
        .flat_map(|c| {
            let name = c["check"].as_str().unwrap_or_default().to_owned();
            c["problems"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|p| p.as_str())
                .map(move |p| format!("sage check {name}: {p}"))
                .collect::<Vec<_>>()
        })
        .collect())
}

/// A card file as a fragment.
///
/// A SAGE card carries its manifest in a `sage` chunk: the content is the PNG without that
/// chunk, and the manifest's digest must match it. Any other card gets a manifest written for
/// it. PNG cards are kept in canonical form (chunks re-written with correct CRCs, nothing after
/// `IEND`), so exporting and re-importing gives the same digest.
fn card_fragment(
    source: &Path,
    bytes: &[u8],
    options: &CardOptions,
    warnings: &mut Vec<String>,
) -> Result<(Files, String), String> {
    let png = bytes.starts_with(&sage_schema::png::SIGNATURE)
        || source
            .extension()
            .is_some_and(|e| e.eq_ignore_ascii_case("png"));
    let read = if png {
        card::read_png(bytes)
    } else {
        card::read_json(bytes)
    };
    let Some(card) = read.card.filter(|_| read.ok) else {
        let why: Vec<String> = read
            .findings
            .iter()
            .filter(|f| f.severity == Severity::Error)
            .map(|f| f.message.clone())
            .collect();
        return Err(format!(
            "{} is not a usable character card: {}",
            source.display(),
            why.join("; ")
        ));
    };
    if png {
        let canonical = sage_schema::png::with_text_chunks(bytes, &[card::SAGE_KEYWORD], &[])
            .map_err(|e| {
                format!(
                    "{}: the PNG is damaged ({e}); open and save it again first",
                    source.display()
                )
            })?;
        if let Some(embedded) = card::sage_manifest(bytes) {
            if *options != CardOptions::default() {
                return Err(
                    "this SAGE card carries its own manifest; --id, --version and --license \
                     apply only to plain card files"
                        .into(),
                );
            }
            let text = embedded.map_err(|e| format!("{}: {e}", source.display()))?;
            return Ok((Files(vec![("card.png".into(), canonical)]), text));
        }
        if canonical != bytes {
            warnings.push(
                "card.png was stored in canonical form (CRCs rewritten, bytes after IEND dropped)"
                    .into(),
            );
        }
        let manifest = written_manifest(&card, "png-card", options, warnings);
        return Ok((Files(vec![("card.png".into(), canonical)]), manifest));
    }
    let manifest = written_manifest(&card, "json", options, warnings);
    Ok((Files(vec![("card.json".into(), bytes.to_vec())]), manifest))
}

/// A manifest for a plain card, with each default reported.
fn written_manifest(
    card: &sage_schema::card::Card,
    format: &str,
    options: &CardOptions,
    warnings: &mut Vec<String>,
) -> String {
    let name = card.name.split_whitespace().collect::<Vec<_>>().join(" ");
    let id = options
        .id
        .clone()
        .unwrap_or_else(|| format!("local.{}", slug(&name)));
    let version = match &options.version {
        Some(version) => version.clone(),
        None if semver::Version::parse(card.character_version.trim()).is_ok() => {
            card.character_version.trim().to_owned()
        }
        None => {
            warnings.push("the card has no semver version; installed as 0.1.0".into());
            "0.1.0".into()
        }
    };
    let license = match &options.license {
        Some(license) => license.clone(),
        None => {
            warnings.push(
                "the card states no license; recorded LicenseRef-Unspecified (set --license)"
                    .into(),
            );
            "LicenseRef-Unspecified".into()
        }
    };
    let title: String = name.chars().take(120).collect();
    let creator = id.split_once('.').map(|(c, _)| c).unwrap_or_default();
    let quote = |s: &str| serde_json::to_string(s).expect("strings serialize");
    format!(
        "schema: sage.fragment/1\nid: {}\nkind: agent\nversion: {}\nengine: {}\ntitle: {}\n\
         creator:\n  handle: {}\nlicense: {}\ncontent:\n  format: {format}\n  tavern_compatible: true\n",
        quote(&id),
        quote(&version),
        quote(&format!(">={ENGINE_VERSION}")),
        quote(&title),
        quote(creator),
        quote(&license),
    )
}

/// Lowercase letters and digits joined by single hyphens, at most 64 characters.
fn slug(name: &str) -> String {
    let mut out = String::new();
    for c in name.chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c.to_ascii_lowercase());
        } else if !out.is_empty() && !out.ends_with('-') {
            out.push('-');
        }
    }
    let mut out: String = out.trim_end_matches('-').chars().take(64).collect();
    while out.ends_with('-') {
        out.pop();
    }
    if out.is_empty() {
        "character".into()
    } else {
        out
    }
}

/// An installed fragment version, verified against its recorded digest.
pub struct Installed {
    /// Its manifest.
    pub manifest: Manifest,
    /// Its content digest, recomputed and equal to the manifest's.
    pub digest: String,
    files: Files,
}

impl Installed {
    /// Reads and verifies an installed version directory.
    pub fn open(dir: &Path) -> Result<Installed, String> {
        let files = Files::read_dir(dir)?;
        let text = files
            .get(MANIFEST_FILE)
            .ok_or_else(|| format!("no {MANIFEST_FILE}"))
            .and_then(|b| {
                String::from_utf8(b.to_vec()).map_err(|_| "manifest is not UTF-8".into())
            })?;
        let manifest = valid_manifest(&text).map_err(|p| p.join("; "))?;
        let recorded = manifest
            .integrity
            .as_ref()
            .map(|i| i.digest.clone())
            .ok_or("the installed manifest has no digest")?;
        let digest = files.digest()?;
        if digest != recorded {
            return Err(format!(
                "its files changed after install (recorded {recorded}, now {digest})"
            ));
        }
        Ok(Installed {
            manifest,
            digest,
            files,
        })
    }

    /// Finds `id`, at exactly `version` or else the highest installed version, in `world`'s
    /// library, and verifies it.
    pub fn find(world: &Path, id: &str, version: Option<&str>) -> Result<Installed, String> {
        let dir = library_path(world).join(id);
        if !safe_name(id) || !dir.is_dir() {
            return Err(format!(
                "{id} is not installed in {}",
                library_path(world).display()
            ));
        }
        let chosen = match version {
            Some(version) => version.to_owned(),
            None => std::fs::read_dir(&dir)
                .map_err(|e| format!("{}: {e}", dir.display()))?
                .filter_map(|e| e.ok()?.file_name().into_string().ok())
                .filter_map(|v| semver::Version::parse(&v).ok())
                .max()
                .ok_or_else(|| format!("{id} has no installed versions"))?
                .to_string(),
        };
        let path = dir.join(&chosen);
        if !safe_name(&chosen) || !path.is_dir() {
            return Err(format!("{id}@{chosen} is not installed"));
        }
        Installed::open(&path).map_err(|e| format!("{id}@{chosen}: {e}"))
    }

    /// One of its files.
    pub fn file(&self, path: &str) -> Option<&[u8]> {
        self.files.get(path)
    }

    /// The agent an installed agent fragment holds.
    pub fn agent(&self) -> Result<ImportedAgent, String> {
        if self.manifest.kind != Kind::Agent {
            return Err(format!(
                "{} is not an agent fragment",
                self.manifest.id.as_str()
            ));
        }
        usable_agent(&self.manifest, &self.files)
            .map(|(agent, _)| agent)
            .map_err(|p| p.join("; "))
    }
}

/// Runs `sage install` and prints the report.
pub fn run(
    world: &Path,
    source: &str,
    options: &CardOptions,
    digest: Option<&str>,
    registry: Option<&str>,
) -> Result<(), String> {
    if let Some(base) = registry {
        let report = if *options != CardOptions::default() || digest.is_some() {
            install_verified(
                world,
                Err(vec![
                    "--registry installs by id; the registry supplies the manifest and digest"
                        .into(),
                ]),
            )
        } else {
            crate::registry::install(world, source, base)
        };
        return print_report(report, source);
    }
    let verified = if crate::download::is_url(source) {
        crate::download::fetch(source)
            .map_err(|e| vec![e])
            .and_then(|(name, bytes)| verify(&name, Some(bytes), options, true))
    } else {
        verify(Path::new(source), None, options, true)
    };
    let verified = verified.and_then(|mut verified| {
        match digest {
            Some(expected) if expected != verified.digest => {
                return Err(vec![format!(
                    "the content is {}, not the expected {expected}",
                    verified.digest
                )]);
            }
            Some(_) => {}
            None if crate::download::is_url(source) => verified
                .warnings
                .push("downloaded without --digest: nothing pinned what was fetched".into()),
            None => {}
        }
        Ok(verified)
    });
    let mut report = install_verified(world, verified);
    report.set_source(source.to_owned());
    print_report(report, source)
}

fn print_report(report: InstallReport, source: &str) -> Result<(), String> {
    println!(
        "{}",
        serde_json::to_string(&report).expect("reports serialize")
    );
    if report.ok {
        Ok(())
    } else {
        Err(format!("{source} was not installed"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slugs_are_valid_fragment_slugs() {
        assert_eq!(slug("Tamsin Reed"), "tamsin-reed");
        assert_eq!(slug("  Zoë — of the 月! "), "zo-of-the");
        assert_eq!(slug("🌙"), "character");
        let long = slug(&"ab ".repeat(40));
        assert!(long.len() <= 64 && !long.ends_with('-'), "{long}");
        assert_eq!(
            slug(&"abc ".repeat(20)).len(),
            63,
            "a cut never leaves a trailing hyphen"
        );
    }

    #[test]
    fn names_that_could_escape_are_unsafe() {
        for bad in ["..", ".", "a/b", "a\\b", "", "c:"] {
            assert!(!safe_name(bad), "{bad}");
        }
        assert!(safe_name("0.1.0") && safe_name("card.png") && safe_name("local.tamsin-reed"));
    }
}
