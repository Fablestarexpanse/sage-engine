//! The rules a manifest must follow. Each rule adds problems; none stops the others.

use std::collections::BTreeSet;

use crate::manifest::*;
use crate::{MANIFEST_SCHEMA, Problem};

struct Problems(Vec<Problem>);

impl Problems {
    fn add(&mut self, path: impl Into<String>, message: impl Into<String>) {
        self.0.push(Problem {
            path: path.into(),
            message: message.into(),
        });
    }
}

pub(crate) fn check(raw: RawManifest) -> Result<Manifest, Vec<Problem>> {
    let mut p = Problems(Vec::new());

    if raw.schema != MANIFEST_SCHEMA {
        p.add(
            "schema",
            format!("is `{}`; this engine reads `{MANIFEST_SCHEMA}`", raw.schema),
        );
    }

    let id_ok = fragment_id(&mut p, "id", &raw.id);

    let kind = Kind::ALL
        .iter()
        .find(|(name, _)| *name == raw.kind)
        .map(|(_, kind)| *kind);
    if kind.is_none() {
        let names: Vec<&str> = Kind::ALL.iter().map(|(n, _)| *n).collect();
        p.add(
            "kind",
            format!(
                "`{}` is not a kind; use one of {}",
                raw.kind,
                names.join(", ")
            ),
        );
    }

    exact_version(&mut p, "version", &raw.version);
    version_requirement(&mut p, "engine", &raw.engine);

    text(&mut p, "title", &raw.title, 1, 120);
    if let Some(description) = &raw.description {
        text(&mut p, "description", description, 1, 4000);
    }

    if id_ok && raw.creator.handle != creator_of(&raw.id) {
        p.add(
            "creator.handle",
            format!(
                "`{}` must match the id's creator part `{}`",
                raw.creator.handle,
                creator_of(&raw.id)
            ),
        );
    }
    if let Some(foundry_id) = &raw.creator.foundry_id {
        text(&mut p, "creator.foundry_id", foundry_id, 1, 64);
    }

    if raw.license.trim().is_empty() {
        p.add(
            "license",
            "is required; use an SPDX id such as `CC-BY-4.0`, or `LicenseRef-AllRightsReserved`",
        );
    } else if let Err(error) = spdx::Expression::parse(&raw.license) {
        let reason = error.reason;
        p.add(
            "license",
            format!("`{}` is not an SPDX expression ({reason})", raw.license),
        );
    }

    for (i, d) in raw.derived_from.iter().enumerate() {
        let path = format!("derived_from[{i}]");
        if fragment_id(&mut p, format!("{path}.id"), &d.id) && d.id == raw.id {
            p.add(
                format!("{path}.id"),
                "a fragment cannot be derived from itself",
            );
        }
        exact_version(&mut p, format!("{path}.version"), &d.version);
    }

    let mut required = BTreeSet::new();
    for (i, d) in raw.requires.iter().enumerate() {
        let path = format!("requires[{i}]");
        if fragment_id(&mut p, format!("{path}.id"), &d.id) {
            if d.id == raw.id {
                p.add(format!("{path}.id"), "a fragment cannot require itself");
            } else if !required.insert(d.id.as_str()) {
                p.add(
                    format!("{path}.id"),
                    format!("`{}` is required twice", d.id),
                );
            }
        }
        version_requirement(&mut p, format!("{path}.version"), &d.version);
    }

    names(&mut p, "provides.commands", &raw.provides.commands, None);
    names(&mut p, "provides.panels", &raw.provides.panels, None);
    names(
        &mut p,
        "provides.components",
        &raw.provides.components,
        id_ok.then_some(raw.id.as_str()),
    );

    match (kind, &raw.capabilities) {
        (Some(Kind::Plugin), None) => p.add(
            "capabilities",
            "a plugin must list the interfaces it imports (an empty list is allowed)",
        ),
        (Some(Kind::Plugin), Some(capabilities)) => {
            let mut seen = BTreeSet::new();
            for (i, capability) in capabilities.iter().enumerate() {
                let path = format!("capabilities[{i}]");
                if !interface_name(capability) {
                    p.add(
                        path,
                        format!(
                            "`{capability}` is not a versioned interface name like \
                             `sage:core/entities@0.1.0`"
                        ),
                    );
                } else if !seen.insert(capability.as_str()) {
                    p.add(path, format!("`{capability}` is listed twice"));
                }
            }
        }
        (Some(_), Some(_)) => p.add("capabilities", "only plugins have capabilities"),
        _ => {}
    }

    match (kind, &raw.content) {
        (Some(Kind::Plugin), Some(_)) => p.add("content", "plugins have no content section"),
        (_, Some(content)) if !["png-card", "yaml", "json"].contains(&content.format.as_str()) => p
            .add(
                "content.format",
                format!("`{}` is not one of png-card, yaml, json", content.format),
            ),
        _ => {}
    }

    if let Some(integrity) = &raw.integrity {
        let hex = integrity.digest.strip_prefix("sha256:");
        if !hex.is_some_and(|h| {
            h.len() == 64
                && h.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        }) {
            p.add(
                "integrity.digest",
                "must be `sha256:` followed by 64 lowercase hex digits",
            );
        }
    }

    if !p.0.is_empty() {
        return Err(p.0);
    }

    let id = FragmentId(raw.id);
    Ok(Manifest {
        schema: raw.schema,
        kind: kind.expect("checked"),
        version: raw.version,
        engine: raw.engine,
        title: raw.title,
        description: raw.description,
        creator: Creator {
            handle: raw.creator.handle,
            foundry_id: raw.creator.foundry_id,
        },
        license: raw.license,
        derived_from: raw
            .derived_from
            .into_iter()
            .map(|d| Derivation {
                id: FragmentId(d.id),
                version: d.version,
            })
            .collect(),
        requires: raw
            .requires
            .into_iter()
            .map(|d| Dependency {
                id: FragmentId(d.id),
                version: d.version,
                optional: d.optional,
            })
            .collect(),
        provides: Provides {
            commands: raw.provides.commands,
            panels: raw.provides.panels,
            components: raw.provides.components,
        },
        capabilities: raw.capabilities,
        content: raw.content.map(|c| Content {
            format: c.format,
            tavern_compatible: c.tavern_compatible,
        }),
        integrity: raw.integrity.map(|i| Integrity {
            digest: i.digest,
            signature: i.signature,
        }),
        id,
    })
}

fn creator_of(id: &str) -> &str {
    id.split_once('.').map(|(c, _)| c).unwrap_or_default()
}

/// Lowercase letters and digits, hyphens only between them.
fn segment(s: &str, max: usize) -> bool {
    !s.is_empty()
        && s.len() <= max
        && !s.starts_with('-')
        && !s.ends_with('-')
        && !s.contains("--")
        && s.bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

fn fragment_id(p: &mut Problems, path: impl Into<String>, id: &str) -> bool {
    let ok = id
        .split_once('.')
        .is_some_and(|(creator, slug)| segment(creator, 39) && segment(slug, 64));
    if !ok {
        p.add(
            path,
            format!(
                "`{id}` is not a fragment id; use `creator.slug` with lowercase letters, digits \
                 and inner hyphens (creator up to 39, slug up to 64 characters)"
            ),
        );
    }
    ok
}

fn exact_version(p: &mut Problems, path: impl Into<String>, version: &str) {
    if let Err(error) = semver::Version::parse(version) {
        p.add(
            path,
            format!("`{version}` is not a semver version like `1.2.0` ({error})"),
        );
    }
}

fn version_requirement(p: &mut Problems, path: impl Into<String>, requirement: &str) {
    if let Err(error) = semver::VersionReq::parse(requirement) {
        p.add(
            path,
            format!(
                "`{requirement}` is not a version requirement like `^1.2` or `>=0.3, <0.5` \
                 ({error})"
            ),
        );
    }
}

fn text(p: &mut Problems, path: &str, value: &str, min: usize, max: usize) {
    let chars = value.chars().count();
    if value.trim().chars().count() < min {
        p.add(path, "must not be empty");
    } else if chars > max {
        p.add(path, format!("is {chars} characters; the limit is {max}"));
    } else if value
        .chars()
        .any(|c| c.is_control() && c != '\n' && c != '\t')
    {
        p.add(path, "must not contain control characters");
    }
}

/// Names like `interrogate` or `noir.suspicion`: lowercase segments joined by dots. With a
/// prefix, every name must start with `prefix.`.
fn names(p: &mut Problems, path: &str, values: &[String], prefix: Option<&str>) {
    let mut seen = BTreeSet::new();
    for (i, name) in values.iter().enumerate() {
        let path = format!("{path}[{i}]");
        let well_formed = name.len() <= 128 && name.split('.').all(|s| segment(s, 64));
        if !well_formed {
            p.add(
                path,
                format!("`{name}` must be lowercase segments of letters, digits and hyphens, joined by dots"),
            );
        } else if let Some(prefix) = prefix.filter(|pre| !name.starts_with(&format!("{pre}."))) {
            p.add(
                path,
                format!("`{name}` must start with the fragment id: `{prefix}.`"),
            );
        } else if !seen.insert(name.as_str()) {
            p.add(path, format!("`{name}` is listed twice"));
        }
    }
}

/// `namespace:package/interface@semver`.
fn interface_name(name: &str) -> bool {
    let Some((path, version)) = name.split_once('@') else {
        return false;
    };
    let Some((package, interface)) = path.split_once('/') else {
        return false;
    };
    let Some((namespace, package)) = package.split_once(':') else {
        return false;
    };
    [namespace, package, interface]
        .iter()
        .all(|s| segment(s, 64))
        && semver::Version::parse(version).is_ok()
}
