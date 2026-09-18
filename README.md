# SAGE: Synthetic Agent Game Engine

**Worlds are built, not scripted.**

SAGE is an open-source engine for persistent text worlds that players and synthetic agents share. The engine decides what happens: every change is an event in one SQLite log, and the world is rebuilt from that log. Agents act only through the same commands a player types, and they work with no AI at all. A model, local or hosted, is optional.

The core knows no genre. Everything else arrives as a **fragment**: characters as data today (places, items and rules are next), and game mechanics as plugins in sandboxed WebAssembly. Fragments are shared through **[Fragment Foundry](https://fragmentfoundarywebsite.vercel.app)**, a static site whose listings the engine itself builds and checks.

## Status

**v0.1.0 is out:** [download it](https://github.com/Fablestarexpanse/sage-engine/releases/latest) for Windows, macOS or Linux. Milestones M1 to M3 are done, and M4 (player client and Foundry) is all but finished. You can already:

- run a world that survives crashes and replays exactly
- play it in a browser
- bring in Tavern character cards as agents
- install fragments from files, URLs or a registry
- share fragments as packages or SAGE cards

Still to come in M4: the 15-minute stranger test with someone who has never seen SAGE. See [docs/STATUS.md](docs/STATUS.md) for detail.

| Milestone | Scope | State |
|---|---|---|
| M1 | World model: entities, components, space graph, event log, snapshots, clock | done |
| M2 | Plugin seal: WIT API, Wasmtime host, manifest validation, `sage check` | done |
| M3 | Synthetic agents: minds, scripted and LLM drivers, memory, reflection | done |
| M4 | Player client, fragments, releases, Fragment Foundry read path | in progress |
| M5 | Workshop editors, uploads, social layer | not started |
| M6 | Marketplace | not started |

A layer doesn't start until the layer below passes its gate tests ([ADR 0004](docs/adr/0004-build-order-and-milestone-gates.md)).

## Try it

[docs/QUICKSTART.md](docs/QUICKSTART.md) goes from download to playing in a browser, and ships with every release. To build from source instead:

```bash
pnpm --dir client install && pnpm --dir client build    # the browser client, embedded in sage
cargo build --release -p sage-server                     # target/release/sage
cargo run --release -p sage-build -- plugins             # first-party plugins, into target/plugins
```

Then start the demo world, with ten agents, and open <http://127.0.0.1:4700/>:

```bash
target/release/sage run my-world.db --seed worlds/demo-agents/seed.json \
  --plugin target/plugins/sage.dialogue --listen 127.0.0.1:4700
```

Create a character and type `look`, `say good day` (the agents answer), `emote waves` or `go onward`. Stop with Ctrl-C, and start again without `--seed`: nothing is lost.

Rust builds don't need Node. Without the client build, `sage` serves a page explaining how to add it, and any WebSocket client can play at `/ws`.

## What the engine does

- **One source of truth.** Events carry schema versions, and old ones are upgraded as they are read, never rewritten. Snapshots speed up loading and must match a full replay (`sage inspect` checks). A world has one writer at a time.
- **Space is a graph.** Places are joined by named ways, and containment never forms a cycle. What an actor perceives follows from where they are.
- **Agents.** A `sage.mind` is scripted (rules as data), `hybrid` (rules that may ask a model) or `llm`. Agents remember what they perceived, rank memories by recency, importance and relevance (embeddings optional), and reflect. Model replies are checked like player commands, and text from the world is never treated as instructions.
- **Plugins.** WebAssembly components get only the `sage:core` interfaces their manifest declares, under fuel and memory limits. A failing plugin is suspended, and the world carries on. First-party plugins: `sage.dialogue` (`tell`) and `sage.wander`.
- **Players.** `--listen` serves the embedded browser client and a WebSocket protocol (`sage.protocol/1`), with local accounts using argon2id hashes, which are kept out of the event log.

## Fragments

| Command | What it does |
|---|---|
| `sage check <dir>` | Validates a fragment manifest and, for plugins, boots the plugin under its grants |
| `sage card <card.png>` | Reads a Tavern Card (v1–v3, PNG or JSON) and shows the agent it becomes |
| `sage install <world.db> <source>` | Verifies a fragment directory, `.sagepkg`, card file or https URL, and adds it to `<world.db>.fragments/`. `--digest` pins the content. `--registry <url>` installs by id |
| `sage place <world.db> <id>` | Commits an installed agent and its seed memories to a stopped world |
| `sage pack <dir> <out.sagepkg>` | Writes a fragment as one deterministic tar+zstd package |
| `sage export <world.db> <id> <out.png>` | Writes an installed agent as a SAGE card: its Tavern PNG plus a manifest chunk |
| `sage registry build <inputs> <out>` | Builds a static registry (`index.json`, `api/v1/fragments/<id>.json`, files by digest) |

Every fragment is identified by a content digest (sha256 over its files, leaving out the manifest), and installed versions never change. Cards, packages and downloads are all read as hostile input: size limits, path checks, no links, and a card reader fuzzed in CI.

To bring a character card into a world:

```bash
sage card my-character.png
sage install my-world.db my-character.png --license CC-BY-4.0
sage place my-world.db local.my-character
```

Signatures and dependency resolution between fragments are not built yet.

## Optional AI

```bash
sage run my-world.db --llm-url http://localhost:11434/v1 --llm-model llama3.2 \
  --embed-url http://localhost:11434/v1 --embed-model nomic-embed-text
```

Any OpenAI-compatible endpoint works. Keys come from `SAGE_LLM_API_KEY` and `SAGE_EMBED_API_KEY`. Without a model, `hybrid` agents fall back to their rules and `llm` agents stay idle. `sage run` warms the model up at start, and drops answers slower than `--llm-max-wait` (default 30 s). The model paths are tested against stub servers; a first run against local Ollama found the timing issues this setting fixes, and a full real-model conversation is still owed.

## Repository

| Path | What |
|---|---|
| `crates/sage-core` | World model, events, journal, space, commands, perception, scheduler |
| `crates/sage-store` | SQLite event log and snapshots |
| `crates/sage-host` | Wasmtime plugin host |
| `crates/sage-schema` | Manifests, character cards, PNG chunks, content digests (also builds to WebAssembly) |
| `crates/sage-agents` | Minds, drivers, memory, retrieval, reflection, card import |
| `crates/sage-server` | The `sage` binary: run, play, fragments, registry |
| `crates/sage-build` | Builds plugins and the WebAssembly validator |
| `wit/core` | The `sage:core` WIT package plugins build against |
| `plugins/` | First-party plugins |
| `client/` | Browser client (React, TypeScript, Vite) |
| `worlds/` | Setting-neutral demo seeds |
| `docs/` | Status, decisions, ADRs, quickstart, research |

Checks, all run in CI:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
pnpm --dir client test
scripts/check-denylist.sh
```

CI also fuzzes the card reader, and the release workflow builds and smoke-tests Windows, macOS and Linux binaries.

## Read more

- [Quickstart](docs/QUICKSTART.md), and the [stranger test](docs/STRANGER-TEST.md) that gates M4
- [Status](docs/STATUS.md) and [decision log](docs/DECISIONS.md)
- [Architecture decision records](docs/adr/)
- [Founding blueprint](docs/research/03-sage-fragment-foundry-founding-blueprint.md)
- [Contributing](CONTRIBUTING.md)

SAGE v1 (Python) is archived; this repository started over with a clean history ([ADR 0001](docs/adr/0001-fresh-start-archive-v1.md)).

## License

Apache-2.0. See [LICENSE](LICENSE). You can build worlds and fragments on SAGE and share or sell them under any terms you choose. Contributions require the [CLA](CLA.md), which is still a placeholder.
