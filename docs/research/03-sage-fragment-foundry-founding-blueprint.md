# SAGE + Fragment Foundry: Founding Blueprint

## Executive summary

SAGE v2 should be a **Rust engine with an entity-component world model, an event-sourced single source of truth, and WASM Component Model plugins**, shipping as one binary that self-hosts trivially. Fragment Foundry should be a **Next.js + Supabase registry/social site that never runs worlds**, whose pages, compatibility badges, and creation tools all render from manifests the engine itself emits. The two are joined by one shared artifact type — the **fragment** — packaged two ways: Tavern-compatible PNG cards for content and signed WASM packages for code.

The three decisions that matter most, and the evidence behind them:

1. **Rust + Wasmtime + SQLite, not Python or TypeScript.** Bevy's `bevy_ecs` is production-grade and runs headless; Wasmtime is the reference WASM runtime with fuel metering, epoch interruption, and first-class Component Model support, and its Rust API is the most complete. SQLite in WAL mode with a JSON event table is the fastest path to a single source of truth. A TypeScript fallback exists but sacrifices the sandbox story.
2. **The WASM Component Model is the plugin seal.** A WIT world literally *is* "declare what you touch or fail at boot": every host import is a named, typed interface, and a component whose imports the host declines to satisfy cannot instantiate. This makes the v1 sealed-API idea a runtime guarantee rather than a convention. WIT's cross-language support also means a plugin can be Rust, Go, C, Python, or JavaScript while the engine treats them identically.
3. **Apache-2.0 for the engine, not FSL.** FSL's competing-use clause ("substitutes for any other product or service we offer") is exactly the ambiguity v1's decision log flagged, and it can never be resolved by promise alone. Apache-2.0 with a CLA (the Godot/Bevy/Defold pattern) removes it; the Foundry site code can stay proprietary because it is the hosted service.

Everything else in this document follows from those three.

## Locked principles (unchanged from discussion)

- SAGE is the engine, self-hosted; Fragment Foundry never runs worlds.
- Fragments are the unit of sharing: content fragments (PNG cards) and code fragments (signed packages), one vocabulary.
- Everything is manifest-driven; the site cannot know what a manifest does not say.
- Synthetic agents are entities with a mind component driving the player command interface.
- LLMs describe what happened; deterministic code decides what happens.
- Build bottom-up: world model → event log → plugin seal → agents → clients/editors.
- "Worlds are built, not scripted." Space is a graph, not rooms.
- Everything that persists carries a version, and old content must keep working or be migrated by tooling, never by hand (see §D2).

## A. Recommended stack

### Primary: Rust

| Layer | Choice | Why this over alternatives |
|---|---|---|
| Language | Rust (edition 2024) | Only language where the ECS, WASM host, and Component Model tooling are all first-party and mature. Bytecode Alliance built Wasmtime, `wit-bindgen`, and `cargo-component` in Rust. |
| ECS | `bevy_ecs` standalone crate | Runs headless without the Bevy app or renderer. Systems auto-schedule against component queries; new systems match existing entities automatically. Archetype storage gives fast iteration for tick-heavy worlds. Alternatives: `hecs` (smaller, less scheduling) and `flecs` (C, richer relationships but FFI cost). |
| Event store | SQLite (WAL) + `rusqlite`, one `events` table + snapshot table | Embedded, single-file, concurrent readers in WAL mode; fits the "one binary, one folder" self-host story. Marten/EventStoreDB add ops burden a solo developer does not need. Postgres becomes an optional backend once a world outgrows one machine. |
| WASM host | Wasmtime with Component Model | Reference runtime; fuel metering and epoch interruption stop runaway plugins; WIT-typed imports are the seal. Wasmer is viable but its Component Model support lags; wazero is Go-only. |
| Creator scripting | Rhai (embedded, sandboxed) for world-owner scripts; Lua via WASM as a community option | Rhai has step limits, no ambient I/O, and Rust-native bindings. Creator scripts run in the same capability sandbox as plugins. |
| Transport | WebSocket (`tokio-tungstenite`, `axum`) now; WebTransport when Safari ships it | Structured JSON frames (GMCP-style) alongside text. |
| Client | React + TypeScript | Rendered from panel manifests; see §G. |
| Browser build | `wasm-bindgen` build of the engine core | Foundry "try before you download" and shared validation in editors — the same crate validates manifests server-side. |

**AI-assistant effectiveness.** Rust is the language where compiler feedback most directly catches assistant mistakes (ownership, exhaustiveness, `Result` handling), which is a feature for a solo developer relying on Claude Code: the compiler is a second reviewer. The cost is slower iteration on early prototypes.

**Migration risk.** If Rust proves too slow to iterate for one person, the fallback below preserves the architecture; only the sandbox depth is lost.

### Fallback: TypeScript/Node

`becsy` or `miniplex` for ECS, `better-sqlite3` for the event log, plugins as **isolated-vm** or QuickJS sandboxes with a manual capability table. This keeps the world model, event sourcing, manifests, and fragment formats identical, and shares one language with the Foundry and client. What it loses: Component Model type safety, fuel-metered determinism, and cross-language plugins. Choose this only if Rust velocity fails a time-boxed trial (recommended: a two-week spike building milestone M1 in each).

### Rejected

- **Python.** v1's language; GIL and lack of a native WASM host make the sandbox story weak. Keep Python only for offline tooling (ComfyUI bridges, migration scripts).
- **Elixir/BEAM.** Excellent concurrency and hot reload, but ECS and WASM Component Model tooling are immature, and it adds a third language to a solo project already spanning Rust and TypeScript.

## B. Core engine architecture

### World model

The minimum universal foundation: **entities** (opaque IDs), **components** (typed, serializable data), **systems** (behavior over component queries), an **event bus**, a **containment/space graph**, **identity and capabilities**, and a **scheduler**. An entity is nothing but the sum of its components, and a system operates on whatever entities carry the components it queries. A corporation, a dragon, and a weather front are all entities; nothing about genre is encoded.

Space is a graph of `Place` entities with `Link` components (direction, traversal rules). "Room" is one shape of place; a coordinate grid, a ship deck, or an abstract social space are others. This directly retires the "room-based" description.

### Event sourcing as the single source of truth

Every state change is an appended event; current state is a projection rebuilt from events plus periodic snapshots. Event sourcing gives an append-only log, full audit history, and the ability to reconstruct past states. The v1 Redis-then-Postgres split is eliminated: in-memory ECS state is a *cache of the projection*, not a second truth, and a crash replays from the last snapshot.

Consequences that fall out for free:
- Agent memory is a projection over the log (§C).
- Fragment upgrades ship migrations as event transformers.
- Debugging is time travel.

### Scheduler

A fixed tick (v1's 4 Hz is reasonable) with a world clock, timers, and scheduled events. Systems run in a deterministic order; agents get a "thinking budget" per tick so LLM latency cannot stall simulation.

### Plugin seal via the Component Model

A plugin is a WASM component whose WIT `world` declares imports (what it may call: `sage:core/entities`, `sage:core/events`, `sage:economy/wallet`) and exports (what it provides: systems, commands, components). WIT interfaces are typed, named, and cross-language; the host only links imports the manifest's `capabilities` list authorizes. If a component imports an interface the manifest does not declare, instantiation fails at boot. That is the seal, enforced by the linker.

### Sandbox limits

Wasmtime fuel metering charges per instruction and traps on exhaustion; epoch interruption is the cheaper wall-clock alternative. Memory limits are set per store. Each plugin gets a per-tick fuel budget; a plugin that exhausts it is suspended and the event is logged — the world keeps running.

**Trust tiers.** Community plugins: sandboxed only. First-party plugins: same sandbox, same manifest — no native escape hatch in v1. Foundry VTT's unsandboxed JavaScript is the cautionary example: every module has full access to the host, and the ecosystem depends on social trust. Roblox's Luau sandbox is the positive example.

**Hot-path cost.** Component calls cross a boundary; for tick-heavy systems (combat resolution) batch the work per tick and pass arrays, not per-entity calls. If profiling shows a hot plugin cannot meet budget, the answer is a better host interface, not a native tier.

## C. Synthetic agent architecture

An agent is an entity with a `Mind` component. It has no privileged API: it emits the same command frames a player emits, and it perceives through the same event stream a client would receive. This single rule keeps agents honest, replayable, and independent of any plugin.

### Drivers (swappable, declared in the mind component)

| Driver | Uses AI | Purpose |
|---|---|---|
| `scripted` | No | Behavior tree or utility AI; the zero-AI baseline every agent must have. |
| `heuristic` | No | Needs-based (GOAP-style) planning over declared goals. |
| `llm` | Yes | Generative-agent loop: observe → retrieve → reflect → plan → act. |
| `hybrid` | Escalating | Heuristic by default; LLM invoked only for dialogue or novel situations. |

### Memory as a projection

Generative agents (Park et al. 2023) keep a memory stream, retrieve by recency/importance/relevance, and periodically reflect to synthesize higher-level memories. In SAGE, the memory stream *is* the agent's filtered view of the event log; importance scores and reflections are events the agent appends; embeddings live in a rebuildable local vector cache (never canonical). Wipe the cache and it regenerates from the log.

### Cost and latency control

- Tick-aligned budgets: an agent may think at most every N ticks; between thoughts it executes its last plan.
- Local models via Ollama/LM Studio/llama.cpp by default; cloud endpoints optional.
- Batch prompts across agents in one location.
- Structured decoding (JSON schema) for actions so the parser never sees free text.

### Guardrails

Player chat reaching an LLM driver is data, never instruction: it is wrapped, labeled, and the driver's output is a *command*, which the deterministic engine then validates like any player command. An agent cannot do anything a player in its position could not do.

### Tavern card mapping

Tavern Card v2 fields map onto the mind component: `description`/`personality` → persona; `scenario` → initial goals; `first_mes`/`mes_example` → voice examples; `character_book` → seed memories. Importing existing cards from Chub/SillyTavern is a converter, not a new format.

## D. Fragment specification

### Manifest (shared by both fragment kinds)

```yaml
# fragment.yaml — schema version 1
schema: sage.fragment/1
id: promptwaffle.noir-detective          # reverse-domain namespace: creator.slug
kind: agent                               # agent | place | zone | item | quest | lorebook | ruleset | world | plugin
version: 1.2.0                            # semver
engine: ">=0.3 <0.5"                      # engine compat range (semver req)
title: The Noir Detective
creator:
  handle: promptwaffle
  foundry_id: usr_01H...                  # optional, set on publish
license: CC-BY-4.0                        # SPDX id, or "LicenseRef-AllRightsReserved"
derived_from:                             # remix attribution, chain preserved
  - id: someone.hardboiled-template
    version: 0.9.1
requires:                                 # dependencies, resolved by semver
  - id: sage.dialogue
    version: "^1"
  - id: sage.economy
    version: "^2"
    optional: true
provides:                                 # what this fragment adds (rendered by site/client/editor)
  commands: [interrogate]
  panels: [case-board]
  components: [Suspicion]
capabilities:                             # code fragments only: WIT imports requested
  - sage:core/entities
  - sage:core/events
  - sage:economy/wallet
content:                                  # content fragments only
  format: png-card | yaml | json
  tavern_compatible: true
integrity:
  digest: sha256:...
  signature: sigstore:...                  # or minisign
```

Design sources: npm's `package.json` (dependencies, semver ranges), Cargo's `[package]`/`[dependencies]`, Foundry VTT's `module.json` (`compatibility.minimum/verified/maximum`, `relationships`), Fabric's `fabric.mod.json` (`depends`, `entrypoints`), VS Code's `contributes` block (the model for `provides`), and OCI's digest-addressed manifests.

### Engine self-description

```yaml
# emitted by `sage describe --json` on each release
schema: sage.engine/1
version: 0.4.0
api:
  wit_package: sage:core@0.4.0
  interfaces: [entities, events, space, identity, scheduler, lexicon]
components: [Describable, Located, Container, Ownable, Link, Mind, ...]
events: [EntityCreated, ComponentSet, Moved, Said, ...]
commands: [look, go, say, emote, tell, who, help, inventory, take, drop, examine, quit]
tools:
  - id: sage-cli
  - id: sage-worldforge
  - id: sage-mcp
manifest_schemas:
  fragment: https://fragmentfoundry.com/schema/fragment/1.json
docs: https://fragmentfoundry.com/docs/0.4.0
```

The Foundry ingests this on release and regenerates docs navigation, feature grids, tool downloads, and compatibility matrices.

### Content fragments: PNG card encoding

Tavern Card v2 stores a Base64-encoded JSON payload in a `tEXt` chunk keyed `chara`; the v3 spec adds a `ccv3` chunk in the same location. SAGE cards:

- Keep the `chara` chunk (v2 JSON) so SillyTavern/Chub/CharacterBinder read the card unchanged.
- Add a `sage` chunk containing the full fragment manifest plus SAGE-specific data. Because `tEXt` is Latin-1 only, Base64 the payload (as Tavern does); use `iTXt` for future UTF-8 text but never `zTXt` (compressed) for the manifest, so structural sniffing stays cheap.
- Size: keep payload under 1 MiB; anything larger is a package, not a card.
- **Structural detection first, label second** (the `cardShape` lesson): the importer decodes every recognized chunk, infers kind from payload shape, and reports mismatches rather than trusting the keyword.
- Fuzz the chunk parser; CharacterBinder v1.8 found a crafted 32-byte PNG could hang a tab via signed-length overflow.

### Code fragments: package format

- Archive: `.sagepkg` (tar+zstd) containing `fragment.yaml`, `plugin.wasm` (a Component Model component), `README.md`, `migrations/`, optional `assets/`.
- The component's WIT world must equal the manifest's `capabilities` (checked at publish and at boot).
- Cross-language: authored in Rust, Go, C, Python, or JS via `wit-bindgen`/`componentize-*`.

### Signing and provenance

Use **Sigstore/cosign keyless signing** for published fragments (creator identity via OIDC through the Foundry), storing the certificate and signature in the manifest's `integrity` block; `minisign` as the offline/air-gapped alternative. Sigstore already signs npm and PyPI packages, so the pattern is proven and free.

### Versioning, resolution, migrations

- Semver strictly; breaking changes to a fragment's `provides` or events are major bumps.
- Resolver: PubGrub-style (as used by Cargo and uv), which produces human-readable conflict explanations — important for laypeople.
- A fragment upgrade may ship `migrations/<from>-<to>.wasm`, a component that transforms stored events/snapshots; the engine snapshots before applying and refuses if the migration touches components outside the fragment's seal.

## D2. Evolution and compatibility contract

The engine will change. Worlds and fragments people have built must survive those changes without the owner rewriting them by hand, and the Foundry must be able to tell everyone, automatically, what still works. This is a founding rule, not a later feature: the M1 gate does not pass until an event written by engine version A is read correctly by engine version B.

### 1. Everything that persists carries a version

| Thing | Where the version lives | On change |
|---|---|---|
| Event types | `schema_version` field on every stored event | Old events are **upcast** on read (converted to the current shape by a registered upcaster); the log is never rewritten |
| Component schemas | version in the component's type registration | A component migration transforms stored snapshot data; old snapshots stay readable |
| WIT interfaces | semver on the `sage:core@x.y.z` package | Host serves an adapter for the previous major until the deprecation window closes |
| Manifest schemas | `schema: sage.fragment/N`, `sage.engine/N` | `sage-schema` reads every published schema version forever |
| Fragments | semver in `fragment.yaml` | Breaking changes to `provides` or emitted events are major bumps |

Nothing can be migrated that cannot be identified, so unversioned persisted data is a CI failure.

### 2. The engine publishes a policy, not just a number

- **N-1 rule:** the current engine runs plugins built against the previous major WIT version through adapters.
- **Deprecation window:** an interface marked deprecated stays available for two minor releases, then is removed in the next major. Deprecated imports log a warning at boot, never a failure.
- **Stable core, unstable edges:** `sage:core` interfaces change slowly and carry the N-1 guarantee; first-party plugin interfaces (`sage:economy`, `sage:dialogue`) may move faster and say so in their manifests.
- `sage describe` includes `supported_wit_versions` and `deprecations` so the Foundry can render them.

### 3. Verification is a command, and the Foundry runs it for everyone

`sage check <fragment> --engine <version>` does, in order: manifest validation, WIT import check against that engine's published API, dependency resolution, and a dry boot in a sandbox with fuel limits. Exit code and a machine-readable report.

The Foundry runs `sage check` for every listed fragment against every new engine release, using the engine's own WASM build, and:
- updates the compatibility badge automatically ("verified on 0.5", "broken on 0.5: undeclared import `sage:core/space@0.4`")
- notifies the creator with the report
- hides broken fragments from the default browse view after a grace period, never deletes them

This is what crates.io does with Crater runs and what Foundry VTT approximates by hand with `compatibility.verified`.

### 4. Migration belongs to the fragment; the safety rail belongs to the engine

- A breaking fragment upgrade ships `migrations/<from>-<to>.wasm`, a sandboxed component that transforms that fragment's events and snapshot data.
- The engine snapshots before applying, refuses a migration that touches components or events outside the fragment's seal, and rolls back on failure.
- For data-only content (agent cards, places, items), migrations are schema transforms the Foundry can run in the browser: a one-click "upgrade this card to the current schema."
- World owners get `sage upgrade --dry-run`, which lists every migration that would run and what it touches, before anything changes.

### 5. A conformance suite fragment authors can run

The engine ships golden-file tests (`sage conformance`): a fixed set of worlds and event logs from each prior release. A new engine version must replay every one identically. Fragment authors get a smaller version for their own fragments, so "does my plugin still work on 0.5" is a local command, not a guess.

### CI invariants added by this section
- Every stored event, component snapshot, and manifest carries a schema version (fails on any unversioned write).
- The oldest supported event log in the conformance suite replays to a byte-identical snapshot on the current engine.
- A plugin built against WIT N-1 boots on engine N through adapters; a plugin built against N-2 fails with a clear message.
- `sage check` output is stable JSON; the Foundry's badge renderer is tested against it.

## E. Fragment Foundry architecture

### Registry

- **Storage:** Cloudflare R2 (S3-compatible, no egress fees) behind Cloudflare CDN for fragment blobs and engine releases; digest-addressed keys.
- **Metadata:** Supabase Postgres; tables `fragments`, `versions`, `manifests` (JSONB), `creators`, `dependencies`. Postgres full-text search suffices at launch; Meilisearch when faceted browse gets slow.
- **Upload pipeline:** browser uploads to R2 via signed URL → edge function validates the manifest with the *engine's own validation crate compiled to WASM* → verifies signature → indexes. The site cannot drift from the engine's rules because it runs the engine's code.
- **Install protocol:** `sage install promptwaffle.noir-detective@^1` → `GET /api/v1/fragments/{id}` → resolver → download by digest → verify → install. Modeled on Modrinth's clean versioned API.

### Manifest-rendered pages

Fragment pages, docs, compatibility badges ("works with SAGE 0.3–0.4"), and the engine feature grid are generated from `sage describe` output and fragment manifests. Marketing copy is the only hand-written text.

### Workshop (local-first creation tools)

Browser-only (CharacterBinder's Tauri-removal lesson: the shell added nothing the browser could not do). Library in IndexedDB/OPFS; optional WebGPU local model for text sorting; exports fragment files. The engine's WASM build provides live validation and a "test this agent" sandbox. An MCP bridge with mutual-HMAC pairing lets Claude Code author fragments into the local library.

### Social layer

Supabase Auth (email, GitHub, Discord). Profiles, follows, likes, comments, collections, changelog feeds, remix graph rendered from `derived_from`. Listing moderation only: reports, takedowns, a DMCA process, and an explicit AI-generated-content policy (CivitAI's experience: a written policy on real-person likeness and minors must exist before launch).

### Heartbeat world directory

A running server may opt in: `POST /api/v1/heartbeat` every 5 minutes with world manifest, player count, connect URL, signed with the server's keypair (first heartbeat registers the key; a token binds it to a creator account). Anti-spoofing: signature + rate limit + optional Foundry-initiated reachability probe. Privacy: player counts only, never names. Modeled on Minecraft server lists and Grapevine's MUD directory.

### Marketplace (sequenced last)

- Merchant of record: **Lemon Squeezy or Paddle** so the Foundry never handles VAT/sales tax itself; Stripe Connect later if payout control matters.
- Low payout floor (≤ $10) and transparent cut; tipping and bounties alongside fixed prices, so the long tail stays alive (Roblox's 100,000-Robux floor is the anti-pattern).
- Paid fragments: authenticated download only. No DRM, no phone-home in the engine. Once downloaded, it runs.
- License field must permit `LicenseRef-AllRightsReserved` for paid content alongside SPDX ids for free content.

## F. Licensing recommendation

| Component | Recommendation | Reason |
|---|---|---|
| Engine (SAGE) | **Apache-2.0** with a CLA | Removes FSL's competing-use ambiguity entirely. Users can build and sell worlds and fragments without a lawyer. Godot (MIT), Bevy (MIT/Apache), and Defold all show permissive engines with healthy ecosystems. Foundry VTT (proprietary, one-time purchase) works because it *is* the product; SAGE's product is the Foundry. |
| First-party plugins, reference world, templates | Apache-2.0 | Same terms as the engine; forks get the whole starter kit. v1 initially shipped plugins with no license at all. |
| Foundry site code | Proprietary (or AGPL if a moat is wanted) | The hosted service is the business; AGPL prevents a silent hosted clone while allowing self-host. |
| Fragment manifests | SPDX id required; `LicenseRef-*` allowed | Buyers must always know terms. |

**Flag for a lawyer:** the CLA text, the AI-generated-content and likeness policy, and the merchant-of-record contract. The FSL question itself does not need a lawyer once Apache-2.0 is chosen — that is the point.

## G. Client and editor model (designed now, built last)

- **Protocol:** JSON frames over WebSocket, two channels multiplexed: `text` (narration, chat) and `state` (typed updates keyed by component/panel). This is the GMCP idea — out-of-band structured data so clients render maps, vitals, and inventories without scraping prose.
- **Panels:** fragments declare panels in `provides.panels` with a schema; the React client renders them from declarations (forms, lists, bars, maps). No plugin JavaScript in v1; a reserved `kind: module` for later, exactly as v1 decided.
- **Editors:** browser-only, in the Foundry workshop, sharing the engine's WASM validation. A world's structural editor (places/links graph) is the first tool after M4.
- **MCP:** one MCP server exposing fragment CRUD, validation, and "play a command as this agent" — the same surface the workshop uses.
- **Accessibility:** text remains authoritative; every panel has a text equivalent; keyboard-complete from day one.

## H. Repository structure and CI invariants

**Monorepo** (Cargo workspace + pnpm workspace) for engine, first-party plugins, schemas, and the client; **separate private repo** for any proprietary world from commit one; **separate repo** for the Foundry site (different license, different deploy cadence).

```
sage/
  crates/
    sage-core        # ECS, events, space graph, scheduler
    sage-store       # SQLite event log, snapshots, migrations
    sage-host        # Wasmtime host, seal, fuel
    sage-schema      # manifest types + validation (compiled to WASM for the site)
    sage-agents      # Mind component, drivers
    sage-server      # axum, WebSocket, CLI
  wit/               # sage:core WIT package (the public API)
  plugins/           # first-party components, each with fragment.yaml
  worlds/demo/       # setting-neutral four-place demo
  client/            # React player client
  docs/adr/          # architecture decision records
```

**CI invariants (each is a test, not a rule):**
- The demo world boots and plays with every AI driver disabled.
- No setting terms in engine crates (denylist sourced from shipped worlds).
- Every manifest round-trips through `sage-schema` in Rust and in its WASM build identically.
- PNG chunk parser fuzzed (cargo-fuzz) on every push.
- A plugin importing an undeclared WIT interface fails to boot (negative test).
- Replaying the event log reproduces the snapshot byte-for-byte.

**Decision hygiene:** ADRs, one file per decision, with a "supersedes" field. A scope gate at each milestone: nothing from the next layer merges until the gate's tests pass.

## I. Build order and milestone gates

| Milestone | Scope | Pass criteria |
|---|---|---|
| **M1 World model** | `sage-core` + `sage-store`: entities, components, space graph, events, snapshots, tick | A 4-place world with 100 entities runs 24 h; kill -9 and restart reproduces state from log; replay test green; an event log written by build A replays correctly on build B after a deliberate event-schema change (upcaster proven). |
| **M2 Plugin seal** | `sage-host`, WIT package, `sage-schema`, first plugin (`sage.dialogue`) | Plugin with undeclared import fails boot; fuel exhaustion suspends plugin without stalling world; manifest validation identical native and WASM; `sage check` exists and a plugin built against WIT N-1 boots through an adapter. |
| **M3 Agents** | `Mind` component, scripted + heuristic drivers, then LLM driver | Ten scripted agents run offline for 1 h; LLM agent passes the "same command interface" test; zero-AI CI invariant green. |
| **M4 Client + Foundry MVP** | WebSocket protocol, React client, `sage install`, registry read path, fragment upload | A stranger installs the engine, downloads a fragment from the Foundry, and plays in under 15 minutes. |
| **M5 Workshop + social** | Browser editors, MCP bridge, accounts, profiles, heartbeat directory | A non-programmer builds and publishes an agent card without a terminal. |
| **M6 Marketplace** | Merchant of record, paid fragments, tipping | First paid fragment sold and installed with no DRM. |

## Risk register and do-not-build list

**Do not build in engine v1:** combat, levels, classes, magic, factions, weather, crafting, economy (all fragments); a native plugin tier; Redis or any second state store; a desktop editor; plugin-shipped client JavaScript; hosted worlds of any kind; more than one client.

**Do not build in Foundry v1:** payments; live moderation of gameplay; a forum; federation; a second registry format.

| Risk | Mitigation |
|---|---|
| Rust velocity too low for one person | Two-week M1 spike in Rust and TS; decide with data. |
| Component Model churn (WASI 0.3 in flight) | Pin Wasmtime; keep WIT package small; only stable features. |
| Fragment-format fragmentation (Forge/Fabric lesson) | One manifest schema, versioned, validated by one crate everywhere. |
| LLM agents drift, hallucinate, or cost too much | Every agent has a scripted fallback; budgets per tick; structured decoding. |
| Marketplace creates legal exposure | Merchant of record; written content policy before launch; sequence last. |
| Proprietary world leaks into engine again | Separate private repo from commit one; denylist CI test. |
| Solo-developer convolution returns | ADRs + milestone gates; nothing from layer N+1 before layer N's tests pass. |

## Open questions for the owner

1. Approve Apache-2.0 + CLA for the engine (this retires FSL and its ambiguity)?
2. Rust primary with a two-week TS spike as insurance — or TS primary from the start?
3. Fragment namespace format: `creator.slug` (proposed) or `@creator/slug` (npm style)?
4. Should agent cards ship the v2 `chara` chunk by default (maximum compatibility) or only on explicit "Tavern export"?
5. Merchant of record preference when the marketplace arrives: Lemon Squeezy, Paddle, or Stripe Connect?
6. Name of the setting-neutral demo world, and whether Rivermoot's design is reused as content only (not code).
