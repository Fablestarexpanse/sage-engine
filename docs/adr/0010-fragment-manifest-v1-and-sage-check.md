# 0010 — Fragment manifest v1 and `sage check`

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M2's gate needs manifest validation that gives identical results natively and in WASM, and a `sage check` command. Everything downstream renders from manifests: the Foundry, install, and the compatibility badges.

## Decision

**`sage.fragment/1`** is defined only by `crates/sage-schema`. Its fields: `schema`, `id`, `kind`, `version`, `engine`, `title`, `description`, `creator{handle, foundry_id}`, `license`, `derived_from`, `requires`, `provides{commands, panels, components}`, `capabilities`, `content{format, tavern_compatible}` and `integrity{digest, signature}`. Unknown fields are refused; a new field means a new schema version.

The rules:
- **Id:** `creator.slug` (owner ruling). Lowercase letters and digits, with hyphens only between them; the creator part is up to 39 characters and the slug up to 64. `creator.handle` must equal the creator part.
- **Kinds:** agent, place, zone, item, quest, lorebook, ruleset, world, plugin.
- **Versions:** `version` is exact semver. `engine` and `requires[].version` are Cargo-style requirements, so ranges are comma-separated (`>=0.3, <0.5`), not the space-separated form in the blueprint example.
- **License:** a valid SPDX expression, with `LicenseRef-*` allowed for paid or all-rights-reserved content.
- **Relations:** no self-derivation, no self-dependency, no duplicate dependencies.
- **Provides:** names are lowercase dotted segments with no duplicates. Components must be prefixed with the fragment id, so two fragments can't claim the same component name.
- **Capabilities:** plugins must list them (an empty list is allowed). Each one is a versioned interface name, with no duplicates. Other kinds must not have capabilities, and plugins must not have `content`.
- **Integrity:** the digest is `sha256:` plus 64 lowercase hex digits. The signature format waits for signing (M4).
- **Limits:** a manifest is capped at 64 KiB before parsing. YAML parsing uses `serde-saphyr`, which never panics on bad input and has a node budget against alias bombs.

Validation reports **every** problem, each with a path such as `requires[1].version`, in document order. `Report::to_json` is the stable wire form. A valid report carries the normalized manifest.

**WASM build.** `crates/sage-schema/wasm` wraps the crate as a component exporting `sage:schema/validator@0.1.0` (`validate-manifest: func(text) -> string`). It has no imports. It's a separate cargo workspace so wasm-only dependencies stay out of the engine. The gate test (`crates/sage-host/tests/schema_wasm.rs`) runs every file in the corpus plus edge cases through both builds and requires byte-identical JSON.

**Corpus.** `crates/sage-schema/tests/corpus/*.yaml`: 3 valid and 18 invalid manifests. The first line of each file names the exact problem paths it must produce, so a rule that stops firing, or fires somewhere new, fails the test.

**`sage check <dir>`** reads `fragment.yaml` (and `plugin.wasm` for plugins) and prints one line of JSON: `{fragment, engine, ok, checks:[{check, status: pass|fail|skipped, problems}]}`. It exits 0 only when every check passes. The checks run in order:
1. `manifest`: validation. If it fails, the rest are skipped.
2. `engine`: the requirement accepts this binary's version. The remaining checks still run.
3. `capabilities` (plugins only): every declared capability is served by this engine, and the component's imports equal the declared capabilities *exactly*. An import that isn't declared fails, and so does a declared capability that's never imported, so a plugin never asks players for a grant it doesn't use.
4. `boot` (plugins only): the plugin loads under its declared grants, its exported name equals the manifest id, and it isn't suspended during one tick on an empty in-memory world within the default limits.

**Test support.** `crates/sage-fixtures` (not published) builds the test plugins (moved there from `sage-host/fixtures`) and the schema validator to components on first use, into `target/`. No binaries are committed.

## Consequences

- The WASM validator is 1.28 MB (release, `opt-level = "s"`), mostly SPDX license data and the YAML parser. That's acceptable for the Foundry's upload path. Trim it before shipping it to browsers.
- `sage check` checks against *this* binary only. The blueprint's `--engine <version>` (checking against another release's published API) needs published `sage describe` output, so it waits for that.
- Not yet covered: the `.sagepkg` archive format, signatures, dependency resolution, and content-fragment payload validation (PNG cards). Those land with install and publish at M4.
