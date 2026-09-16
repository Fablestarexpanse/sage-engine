NEXT: M2 is closed (ADR 0011). Next is M3, synthetic agents. Its plan is not written or agreed yet. Start by agreeing the slice order with the owner. Known inputs: blueprint §C, the ADR 0004 M3 gate (ten scripted agents offline for 1 h, which needs a fast-mode equivalent per the owner's no-long-waits preference; the LLM same-command-interface test; the zero-AI demo in CI), the need for a command interface and perception, and `sage.dialogue` as the first plugin M3 builds.

# Status

| Milestone | State |
|---|---|
| M0 Scaffold | done: workspace, CI (fmt, clippy, test, denylist), ADRs 0001–0004 |
| M1 World model | **closed** 2026-09-16 (ADR 0005-0008; 24 h wall-clock run waived, fast-mode equivalent passed) |
| M2 Plugin seal | **closed** 2026-09-16 (ADR 0009-0011; N-1 WIT adapter test deferred by owner ruling) |
| M3 Agents | next |
| M4 Client + Foundry MVP | blocked on M3 |
| M5 Workshop + social | blocked on M4 |
| M6 Marketplace | blocked on M5 |

## Gate tests not yet written (they arrive with the code they test)

- An event log from before a *real* schema change replays through its upcaster (M1). The mechanism is tested; this test ships with the first real change.
- A plugin built against WIT N-1 boots through an adapter (M2; deferred to the first real `sage:core` major bump, owner ruling)
- The PNG chunk parser is fuzzed (whenever the parser exists)
- The demo world plays with every AI driver disabled (M3)

## Gate tests passing

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

## Open questions for the owner (not blocking M1)

1. ~~Fragment namespace~~: decided `creator.slug` (2026-09-16).
2. Should agent cards write the Tavern v2 `chara` chunk by default, or only on an explicit Tavern export?
3. Merchant of record when the marketplace arrives: Lemon Squeezy, Paddle or Stripe Connect?
4. Name of the setting-neutral demo world.
5. Should world time pass while the server is down? Currently it doesn't: on restart the clock resumes from the last recorded tick (ADR 0006). The alternative is a catch-up step on boot.
