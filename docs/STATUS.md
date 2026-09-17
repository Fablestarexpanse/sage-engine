NEXT: M4 S3a is done (ADR 0023): Tavern Card v1/v2/v3 import (`sage card`), a fuzzed PNG chunk reader, `sage.mind` v3 with voice examples. S3b is `.sagepkg` (tar+zstd) and `sage install` into `<world>.fragments/` with sha256 digest checks, plus a placement step that commits an imported agent and its seed memories as events, and SAGE card export (writes `chara` by default). Then S4 (Foundry read path, release binaries, the 15-minute test). Still owed: runs against real models, and checking the first CI fuzz run.

# Status

| Milestone | State |
|---|---|
| M0 Scaffold | done: workspace, CI (fmt, clippy, test, denylist), ADRs 0001–0004 |
| M1 World model | **closed** 2026-09-16 (ADR 0005-0008; 24 h wall-clock run waived, fast-mode equivalent passed) |
| M2 Plugin seal | **closed** 2026-09-16 (ADR 0009-0011; N-1 WIT adapter test deferred by owner ruling) |
| M3 Agents | **closed** 2026-09-16 (ADR 0012-0020; Tavern Card import moved to M4) |
| M4 Client + Foundry MVP | in progress: S1 done (WebSocket protocol, accounts; ADR 0021), S2 done (browser client; ADR 0022), S3a done (character card import; ADR 0023) |
| M5 Workshop + social | blocked on M4 |
| M6 Marketplace | blocked on M5 |

## Gate tests not yet written (they arrive with the code they test)

- A plugin built against WIT N-1 boots through an adapter (M2; deferred to the first real `sage:core` major bump, owner ruling)

## Gate tests passing

- The PNG card chunk reader never panics or hangs: 20,000 fixed-seed mutations in `cargo test`, plus a coverage-guided cargo-fuzz run in CI (`crates/sage-schema/tests/cards.rs`, `crates/sage-schema/fuzz`)

- Replay from genesis reproduces the live snapshot byte for byte (`crates/sage-store/tests/replay.rs`)
- Restoring a snapshot then replaying the tail gives the same bytes
- The database refuses events with no schema version, and refuses edits or deletes on events
- A refused batch writes nothing; a second writer is refused
- A log or store written by a newer engine is refused
- Space graph and containment: dangling references, destroying a referenced entity, containment cycles and ticks going backwards are all refused, and a refusal mid-batch leaves the world byte-identical
- A failed log append undoes the world change
- A scheduled world (a system moving entities along links, plus idle checkpoints) replays byte-identically and resumes its clock from the log

- A demo world hard-killed mid-run and resumed ends byte-identical to an uninterrupted run (`crates/sage-server/tests/restart.rs`)
- `--seed` is refused on a world that already has a history
- 24 h of world time (345,600 ticks, 864,324 events) in fast mode: `refused=0`, snapshot matches replay, 16 MB peak during replay (ADR 0008)

- A plugin importing an ungranted interface is refused at load, naming the interface; the linker alone also refuses it (`crates/sage-host/tests/seal.rs`)
- Fuel exhaustion and the memory cap each suspend a plugin while the world keeps ticking
- Plugin events are validated like any others (refused, or the plugin is suspended if undecodable), and replay without the plugin

- Manifest validation gives byte-identical reports native and in WASM across the 21-file corpus plus edge cases (`crates/sage-host/tests/schema_wasm.rs`)
- Every corpus manifest produces exactly its expected problem paths (`crates/sage-schema/tests/corpus.rs`)
- `sage check` passes a good plugin and fails, naming the problem, on an undeclared import, an unused or unserved capability, a name mismatch, a runaway plugin, a wrong engine, or a bad or missing manifest (`crates/sage-server/tests/check.rs`)

- `sage run --plugin` refuses a plugin that fails `sage check` before touching the world file; the kill -9 restart gate passes with the `sage.wander` plugin driving the world

- Commands and perception: core verbs, who perceives what, lexicon rendering, refusal and suspension paths, command logs replay (`crates/sage-core/src/command.rs` tests)

- Plugin commands: `sage.dialogue` `tell` reaches only the teller and the target; plugins cannot emit other names' occurrences; `sage check` enforces `provides.commands` (`crates/sage-host/tests/dialogue.rs`, `crates/sage-server/tests/check.rs`)

- Ten scripted agents run one hour of world time (14,400 ticks) in fast mode: `refused=0`, snapshot matches replay, and every action is a logged `sage.command` (`crates/sage-server/tests/agents.rs`)

- A log recorded by old build 2a715f3 (378 `Occurred` v1) replays through the upcaster, is refused without it, and the new engine runs on top of it (`crates/sage-agents/tests/old_logs.rs`), closing the M1 upcaster gate
- Memory rebuilt from the log equals live memory, and a world restarted every 37 ticks matches an uninterrupted one (`crates/sage-agents/tests/memory.rs`)

- A crash on any append mid-tick loses the whole tick, never half of it (`crates/sage-store/tests/replay.rs`)
- LLM agents act only through the player command path; injected text stays data; unreachable or slow models never block ticks and scripted rules take over (`crates/sage-agents/tests/llm.rs`, `crates/sage-server/tests/llm.rs`), all against stub servers
- The demo worlds play with no AI in CI (`crates/sage-server/tests/agents.rs`)

- Component data from older versions is upcast through events and snapshots; a v1 mind still applies (`crates/sage-core/src/world.rs`, `crates/sage-agents/tests/retrieval.rs`)
- A prompt keeps an important old message over repetitive recent chatter (`crates/sage-agents/tests/retrieval.rs`)

- Embeddings find meaning word overlap misses; the cache is reused, rebuildable and never canonical; a failing endpoint falls back to word overlap (`crates/sage-agents/tests/embeddings.rs`)

- Reflections trigger on an importance budget, are logged privately, reach later prompts, and are not redone after a restart (`crates/sage-agents/tests/reflection.rs`)

- Players register, log in and play over WebSocket against the real binary; limits hold; accounts survive restarts; no password material in the log (`crates/sage-server/tests/play.rs`)

## Open questions for the owner (not blocking M1)

1. ~~Fragment namespace~~: decided `creator.slug` (2026-09-16).
2. ~~Tavern `chara` chunk~~: decided, written by default (2026-09-16).
3. Merchant of record when the marketplace arrives: Lemon Squeezy, Paddle or Stripe Connect?
4. Name of the setting-neutral demo world.
5. Should world time pass while the server is down? Currently it doesn't: on restart the clock resumes from the last recorded tick (ADR 0006). The alternative is a catch-up step on boot.
