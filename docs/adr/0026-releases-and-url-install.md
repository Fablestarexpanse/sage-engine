# 0026 — Release binaries and installing from a URL

- **Status:** accepted
- **Date:** 2026-09-17
- **Supersedes:** none

## Context

M4 S4a. Owner rulings:
- releases come first
- the first release is v0.1.0 for Windows x86_64, macOS x86_64 and arm64, and Linux x86_64, as zip/tar.gz with SHA256SUMS
- I ask before pushing the tag that publishes it

The M4 gate is a stranger who installs the engine, downloads a fragment from the Foundry, and plays within 15 minutes. That needs binaries anyone can run, and an install that can fetch.

## Decision

**`sage install <world.db> <https-url> [--digest sha256:…]`**
- **Allowed URLs:** only `https://`. Plain `http://` is allowed only for loopback hosts (local registries, tests). The HTTP client runs `https_only` for every non-loopback fetch, so redirects can't drop to http. At most 5 redirects.
- **Limits:** the body is capped at 64 MiB while it streams, and the whole request at 120 s. A 404 or any other non-success status is refused.
- **Checks:** the bytes go through exactly the checks a local file gets. The URL's last path segment tells a package from a card by extension, and falls back to the content.
- **`--digest`:** pins the content digest, for URLs and local files alike. A mismatch is refused before anything is written. A URL install without `--digest` succeeds, with a warning. The Foundry will hand out URL and digest together.
- **Report:** gains `source`, the path or URL as given.
- **Dependency:** `ureq` 3.4, already used by `sage-agents`, with its default rustls TLS and webpki roots.

**Release workflow** (`.github/workflows/release.yml`).
- **Triggers:**
  - A `v*` tag builds, tests and publishes.
  - A manual run builds and tests the same archives without publishing, named `-dev-<sha>`.
- **Targets and runners:**

  | Target | Runner | Note |
  |---|---|---|
  | `x86_64-pc-windows-msvc` | `windows-latest` | |
  | `x86_64-unknown-linux-gnu` | `ubuntu-22.04` | the oldest glibc on offer |
  | `aarch64-apple-darwin` | `macos-14` | |
  | `x86_64-apple-darwin` | `macos-14` | cross-compiled, so not smoke-tested |

- **Each build:**
  1. builds the browser client, so it is embedded
  2. builds `sage` with `--locked` and the first-party plugins
  3. **smoke-tests** the native binaries: `--version`; 200 ticks of the demo-agents world with `sage.dialogue`, with `refused=0`; `--listen` reporting `client=embedded`; and `sage inspect` reporting that the snapshot matches replay
- **Archive contents:** `sage`, `README.md`, `LICENSE`, `NOTICE`, `QUICKSTART.md`, both demo seeds, and the `sage.wander` and `sage.dialogue` plugins.
- **Tag check:** a tag that doesn't match the workspace version fails the build.
- **Publish:** runs only for tags. It writes SHA256SUMS and creates the GitHub Release, with the quickstart as the notes.

**`docs/QUICKSTART.md`**: the stranger's path. Download and verify, start the demo-agents world with the dialogue plugin, play in the browser, bring in a Tavern card (`card`, `install`, `place`), install from a URL with `--digest`, and optionally connect a local model.

**Version 0.1.0.**
- The workspace, client and first-party plugins move from 0.0.1 to 0.1.0. The plugins' engine ranges become `^0.1.0`, and so do the test fixtures that stated `^0.0.1`.
- The sage-schema WASM and fuzz lockfiles follow.
- Under Cargo's caret rules `^0.0.1` means exactly 0.0.1, so leaving those ranges would have stopped the plugins from loading.

## Consequences

- **Tests:** 3 new, 205 in total.
  - **Unit:** non-https and non-loopback-http URLs are refused.
  - **Against a local HTTP server:**
    - a wrong `--digest` is refused and nothing is written
    - the right digest installs and reports the source
    - no digest installs with a warning
    - `--digest` pins local files too
    - a 404 is refused
    - an endless body stops at 64 MiB
    - a remote `http://` URL is refused
- **Real runs:**
  - **Windows release binary:** I ran every quickstart command. That included installing a card over real HTTPS from `raw.githubusercontent.com`, placing the Tamsin card, and in the browser `look`, `say`, `emote`, `go onward` and `onward`, and `tell`. `tell` only reaches someone in the same place and addresses them by their first word.
  - **Manual release run:** 35237623204 built all four archives, 8.2–9.9 MB each. The Linux smoke test ran 200 ticks with `refused=0`, reported `client=embedded`, and inspect matched. The macOS arm64 and Windows smoke tests passed too.
- **Seen in the real run:**
  - Four commands typed within one tick lost the fourth to the 3-per-tick limit. The client shows that error only until the next command.
  - `tell Tamsin Reed hello` can't address a two-word name. That is a limit of `sage.dialogue`, not of the engine.
- **Not done:**
  - Binaries are not code-signed or notarized. The quickstart explains SmartScreen and `xattr`.
  - The x86_64 macOS binary is built but not run in CI.
  - Releases are not reproducible byte for byte.
- **Next:** publish v0.1.0 when the owner agrees. Then S4b, the Foundry static read path.
