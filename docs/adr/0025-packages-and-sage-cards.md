# 0025 — `.sagepkg` packages and SAGE cards

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M4 S3b, part 2. The blueprint gives fragments two shareable forms:
- **Packages:** tar+zstd archives holding `fragment.yaml`, `plugin.wasm`, `README.md`, `migrations/` and `assets/`.
- **SAGE cards:** Tavern PNGs that keep `chara` and add a `sage` chunk carrying the manifest.

Owner rulings: SAGE cards write `chara` by default; integrity is the digest for now.

## Decision

**`sage pack <fragment-dir> <out.sagepkg>`**
- **Checks:** everything `sage install` checks, except the engine range, since a package may target another engine. That covers the manifest, the digest, a usable card for agents, and `sage check` for plugins.
- **Digest:** if the manifest states none, it is added to the packed manifest. Packages always state their digest.
- **Archive:** a tar with entries sorted by path, mode 0644, owner 0 and time 0, compressed with zstd level 19. The same files always pack to the same bytes.
- **Output:** one line of JSON.

**`sage install` reads packages.** A source is a package when it is named `.sagepkg` or starts with the zstd magic. Unpacking treats the archive as hostile:
- **Entry types:** only regular files and directories. Links, devices and the rest are refused.
- **Paths:** relative, at most 16 components, each a safe file name as for directories. `..`, absolute paths and backslashes are refused.
- **Duplicates:** refused.
- **Limits:** at most 256 files and 64 MiB. The limit is counted while decompressing, and decompression is also capped, so a compression bomb stops at the limit.
- **After unpacking:** a package goes through the same checks as a directory. Plugins are written to a temporary directory for `sage check`.
- **Digest:** it covers the files, not the archive, so a package and its directory install with the same digest.

**SAGE cards: `sage export <world.db> <id>[@version] <out.png>`.** A `png-card` agent fragment exports as its card PNG unchanged, plus one `sage` tEXt chunk: Base64 of `{"schema": "sage.card/1", "manifest": "<fragment.yaml>"}`.
- **Tavern compatibility:** the card's `chara` and `ccv3` chunks stay, so Tavern tools read it as before (verified with CharacterBinder). The report says `tavern_compatible`, and warns if the card has no `chara`.
- **Content:** a SAGE card's content is the PNG with its `sage` chunk removed. The digest in the carried manifest covers exactly that, so the card doesn't need to hash itself.
- **Installing a SAGE card:** `sage install` uses the carried manifest. It refuses `--id`, `--version` and `--license`, and refuses a card whose content doesn't match the digest, for example an edited `chara`. The same fragment installs anywhere with the same id, version and digest, and reports `already-installed` where it already is.
- **Canonical form:** re-written chunks with correct CRCs, and nothing after `IEND`.
  - Plain PNG cards are now stored in canonical form when installed, with a warning if the bytes change, so any installed card can export.
  - Export refuses a card that isn't canonical, and checks the round trip before writing.
- **Size:** card data (`chara`, `ccv3` and `sage` together) is capped at 1 MiB, as the blueprint says. Larger fragments are shared with `sage pack`.
- **Shared code:** `sage_schema::card` gains `sage_chunk` and `sage_manifest`, so the Foundry reads SAGE cards with the same code.

**Not done: `--no-tavern`.** The ruling allows omitting `chara`. But an agent card's content *is* its Tavern data. Without `chara`, a card would either need a `ccv3` chunk (still Tavern) or a SAGE-only card format, which the blueprint rules out ("a converter, not a new format"). Omitting `chara` would also change the content, and so the digest, under the same version. This is left for the owner to decide.

**Dependencies:**
- `tar` 0.4.46.
- `zstd` 0.13.3. I chose it over 0.14.0, which had been out 12 days; 0.13.3 has had 19 months of use.
- `tempfile`, promoted to a normal dependency of `sage-server`.

## Consequences

- **Tests:** 6 new, 202 in total.
  - Unit: packing is deterministic regardless of input order and round-trips; unsafe package paths are refused.
  - Binary:
    - A card fragment directory packs to identical bytes twice. The package and the directory install with the same digest, a nested asset survives, and card options on a package are refused.
    - The first-party `sage.dialogue` plugin packs and installs after its checks.
    - Hostile packages are refused: traversal, absolute path, symlink, duplicate, not zstd, empty, truncated, and a 100 MiB zero-file bomb that compresses below 1 MiB.
    - Export round trip: `sage card` reads the exported card from `chara` and notes the SAGE chunk. It installs elsewhere with the same id, version and digest, and reports already-installed at home. It refuses options. An edited `chara` is refused by digest. A plugin can't be exported.
  - **Mutation checks:**
    - Disabling the path check fails the hostile-package test.
    - Removing the size limit makes the bomb stop only at the decompression cap, with a different message, and the test fails.
- **Real run** (the Tamsin fragment installed in S3b part 1):
  - `sage export` wrote a 2.2 MB SAGE card.
  - CharacterBinder's own decoder, run from its source, still read `chara` → "Tamsin Reed", and listed the chunks `chara, name, sage`.
  - `sage card` read it as OK.
  - Installing it into a new world gave `sage-test.tamsin-reed@0.1.0` with the same digest (`sha256:e32e6228…`). Into the original world it reported `already-installed`.
  - `sage pack` of the installed directory gave a 2.2 MB package, and installing it gave the same digest again.
- **M4 S3 is complete.** Signatures, dependency resolution, uninstalling, listing, and placing into a running world remain.
- **Next:** S4, the Foundry read path, release binaries, and the 15-minute stranger test.
