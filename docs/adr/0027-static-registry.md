# 0027 — Static registry: `sage registry build` and install by id

- **Status:** accepted
- **Date:** 2026-09-17
- **Supersedes:** the "validated by the sage-schema WASM build at build time" part of the S4 plan (DECISIONS, 2026-09-17)

## Context

M4 S4b. Owner rulings:
- The Foundry read path starts as a static index, hosted on Vercel.
- The index is built by `sage registry build`, and the site only renders its output.
- `sage install <world> <id>@<req> --registry <site>` resolves and installs by digest.
- The WASM validator moves to the upload path (M5).
- The v0.1.0 tag waits until the Foundry works.

The blueprint's install protocol is `sage install id@^1` → `GET /api/v1/fragments/{id}` → resolve → download by digest → verify → install. Static files can serve all of that.

## Decision

**`sage registry build <inputs-dir> <out-dir>`**. Each entry directly inside `inputs-dir` is an input:
- a `.sagepkg`
- a SAGE card PNG
- a fragment directory, which is packed

Each is verified with the same `verify` that `sage install` uses, without the engine-range check, so a fragment for a newer engine can be listed. Plugins still pass `sage check`, which boots them on this engine.

Refused inputs:
- plain cards without a manifest (export a SAGE card or pack a fragment first)
- anything else that isn't a fragment
- anything that fails verification
- a second input under an id and version already listed with different content (identical content is merged)

The output:
- **`index.json`** (`sage.registry/1`): `built_by`; every fragment with its versions, newest first; and `refused` inputs with their problems.
- **`api/v1/fragments/<id>.json`**: one fragment: `id`, `kind`, `title`, `latest`, and `versions`. Each version lists `version`, `engine`, `digest` (content digest), `url` (relative), `format` (`sagepkg` or `sage-card`), `bytes`, the normalized `manifest`, `agent` (what a card becomes, for fragment pages) and install `warnings`.
- **`blobs/sha256/<hex>.<ext>`**, named by the sha256 of the *file*. The content digest leaves out the manifest, so two fragments can share content but never a file.

Building is deterministic: sorted inputs, pretty JSON, no timestamps. It writes to a sibling directory and swaps it in. The output directory is replaced only if it is empty or already holds a `sage.registry/1` index. An output nested in the inputs, or the reverse, is refused. Any refusal makes the command exit non-zero, but the registry of accepted inputs is still written, so a site build can fail loudly.

**`sage install <world.db> <id>[@<requirement>] --registry <base-url>`**
1. The id must be a safe `creator.slug`, and the requirement valid semver (default `*`).
2. It fetches `<base>/api/v1/fragments/<id>.json`, which must be `sage.registry/1` for that id.
3. It chooses the newest version that matches the requirement *and* whose engine range accepts this engine. If none matches, it lists every version with its engine range.
4. It refuses a `url` containing `..`, starting with `/`, or containing a scheme.
5. It fetches the file (https-only rules from ADR 0026) and verifies it as any install.
6. The served manifest's id and version, and its content digest, must equal what the registry listed. `--digest` and card options are refused with `--registry`, because the registry supplies them.
7. The report's `source` is `<id>@<version> from <base>`.

## Consequences

- **Tests:** 2 new binary tests against a static file server, 207 in total.
  - **The build:**
    - Inputs are Maren 1.0.0 (directory), 1.1.0 (package), 9.0.0 (engine `>=99`), the dialogue plugin, and three bad inputs.
    - Two fragments and four versions are listed, and exactly the three bad inputs are refused, each with its reason.
    - Versions come newest first. The agent summary and blob sizes match.
    - A second build is byte-identical.
    - Rebuilding over a registry works. A directory holding other files is refused and left untouched, and so is an output nested in the inputs.
  - **Install:**
    - With no requirement it picks 1.1.0, since 9.0.0 needs a future engine. `=1.0.0` pins 1.0.0.
    - `^2` is refused with the list of versions, and so is an unknown id.
    - A path-like id is refused, and so is `--digest` with `--registry`.
    - A registry entry whose digest was edited is refused. So is one pointing at another fragment's file, and one whose url leaves the registry.
  - **Mutation check:** without the listed-versus-served check, the tampered-registry assertions fail.
- **Real run** (release build, Windows):
  - **The build:** from the Tamsin SAGE card and `target/plugins`, it first refused both plugins. Their manifests still said `^0.0.1` because `target/plugins` hadn't been rebuilt after the version bump. After rebuilding the plugins it listed 3 fragments.
  - **Installing:** served by Python's `http.server`, `sage install … sage.dialogue --registry http://127.0.0.1:4801` and `… sage-test.tamsin-reed@^0.1 --registry …` installed with the listed digests.
  - **Playing:** `sage place` put Tamsin in the world. `sage run --plugin <world>.fragments/sage.dialogue/0.1.0` ran 20 ticks with `refused=0`, loading the plugin straight from the library.
- **Not built yet:**
  - The Foundry site (S4b part 2).
  - Signatures.
  - Dependency resolution across fragments (`requires`).
  - A `--plugin` shorthand by installed id.
  - The index is rebuilt whole each time; fine for a static registry at this size.
- **Next:** S4b part 2, the Next.js site in Fragment-Foundary-Web-Site that renders this output, then Vercel.
