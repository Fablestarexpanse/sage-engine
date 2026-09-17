# 0024 — Fragment library: install and place

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M4 S3b, part 1. Owner rulings:
- Installing puts a verified fragment into the world's library, `<world>.fragments/`, filed by id and version. Placing it in the world is a separate step that commits ordinary events. Uninstalling never rewrites history.
- Integrity is checked by sha256 digest now, with signatures later. Unsigned installs say so.

S3a (ADR 0023) turns a card into an agent but writes nothing. This part makes that agent real in a world.

## Decision

**Content digest** (`sage_schema::digest`, so the Foundry's WASM build computes the same value). It is the sha256 of every file except `fragment.yaml`, taken in byte order of path. Each file contributes its path length (u32 BE), its path, its size (u64 BE) and its bytes.
- **Manifest excluded:** leaving `fragment.yaml` out means a manifest can state the digest of its own content.
- **Same files, same digest:** a directory and a future `.sagepkg` package holding the same files get the same digest.
- **Fixed format:** a test pins the format against a hand-built input.

**`sage install <world.db> <source>`**. The source is either a fragment directory or a card file (`.png`/`.json`).
- **Directory checks:**
  - No links.
  - File names use only `[A-Za-z0-9._+-]`.
  - At most 256 files and 64 MiB.
  - The manifest must validate, and its engine range must accept this engine.
- **Card file:** the card becomes a fragment holding `card.png` or `card.json` unchanged, plus a written manifest:
  - `kind: agent`, and `content.format` set to `png-card` or `json`
  - id `local.<name as a slug>`, or `--id`
  - version from the card if it is semver, else `0.1.0`, or `--version`
  - license `LicenseRef-Unspecified`, or `--license`
  - engine `>=<this engine>`

  Each default is reported as a warning.
- **Digest check:**
  - A stated `integrity.digest` must match, or the install is refused.
  - With no digest stated, the computed one is appended to the stored manifest, with a warning.
  - Signatures aren't verified yet. That is reported every time.
- **Kinds:**
  - `agent`: the card must read and convert with no errors. Its warnings carry through.
  - `plugin`: `sage check` must pass on the source.
  - Anything else is refused as not installable yet.
- **Where it goes:** into `<world>.fragments/<id>/<version>/`, written to a temporary sibling and then renamed, so no half-installed version is ever found.
- **Installed versions never change:**
  - Installing the same content again reports `already-installed`.
  - Different content under the same id and version is refused, and the report says to bump the version.
- **Output:** one line of JSON: `{ok, status, fragment, version, kind, digest, path, problems, warnings}`. Installing never creates or opens the world.

**`sage place <world.db> <id>[@version] [--at <place>] [--name <name>]`**.
- **Version:** exactly the one given, or else the highest installed semver.
- **Digest re-check:** the installed files are checked against the recorded digest again, so a file edited after install is refused before the world is touched.
- **Placement is one transaction at the world's current tick:**
  - `EntityCreated`
  - `sage.describable`
  - `sage.actor`
  - `sage.located` (`--at`, or else the lowest-numbered place)
  - `sage.mind`
  - `sage.origin`
  - one `sage.mind.remembered` occurrence per seed memory, with the agent as actor, so the agent alone perceives it
- **Names:** a name already used by an actor (ignoring case) is refused. `--name` places another copy.

**`sage.origin` v1** (core component): `{fragment, version, digest}`. It records which fragment an entity came from, for listing dependencies and for the Foundry. It is validated: digest format, a `creator.slug`-shaped id, and version length.

**Seed memories** (`sage.mind.remembered` v1, `{text}`).
- **Wording:** "You remember: {text}".
- **Importance:** 5 for the agent.
- **Reflection:** they aren't counted towards the reflection budget, since they are what the agent already knew, not new experience.

**Writer lock.** `sage run` and `sage place` hold an exclusive OS lock on `<world>.lock` (`File::try_lock`), and the OS releases it when the process ends. A second writer is refused at once, saying the world is in use. Found by the end-to-end test: `sage place` into a running world succeeded. The log's sequence check (ADR 0005) would only have stopped the *running* server at its next append, after its in-memory world had already diverged. `sage inspect` stays lock-free.

## Consequences

- **Tests:** 10 new, 196 in total.
  - Digest format and properties.
  - Placement events: origin and mind set; the seed memory's audience is exactly the agent; importance 5; its wording; not counted towards reflection; a bad origin refused.
  - `sage install` against the binary:
    - a card installs once; reinstalling reports already-installed; changed content needs a new version
    - `--id`, `--version` and `--license` work
    - no world file is created
    - a lorebook is refused
    - directories are checked against their digest; card options on a directory and unusable kinds are refused
    - the first-party `sage.dialogue` plugin installs, and the same plugin missing a declared capability fails through `sage check`
  - `sage place`:
    - a non-place, an uninstalled id and a missing version are refused
    - a taken name is refused, and `--name` works
    - a file changed after install is refused
    - `sage inspect` still finds the snapshot matches replay
  - End to end: install, place, `sage run --listen`. A second `sage place` and a second `sage run` are refused while it runs. A WebSocket player says the agent's name and hears the card's greeting, and never sees the agent's seed memory.
- **Real run** (Windows, demo-agents world, Tamsin card written by CharacterBinder):
  - Install reported the three expected warnings plus the dropped `system_prompt`.
  - Placing gave entity 119 with 2 memories.
  - `sage place` into the running world was refused.
  - In the browser client, "say Tamsin, can you take me across?" got "Crossing's three coins. Fog's extra. Name?".
  - Inspect after stopping: `snapshot_matches_replay: true`.
- **Seen in the real run:** a scripted demo agent said "Good day, Tamsin Reed", and Tamsin answered with the same canned line. That is expected without a model: the no-model fallback is one line. With a model, rule 1 (`@think`) answers instead.
- **Not built yet:**
  - `.sagepkg` packages
  - SAGE card export (`chara` + `sage` chunks)
  - placing into a running world (it needs an in-world command or admin channel)
  - listing and uninstalling
  - non-agent content kinds
  - Seed memories can age out of the 256-memory window like any memory.
- **Next:** S3b part 2, `.sagepkg` and card export.
