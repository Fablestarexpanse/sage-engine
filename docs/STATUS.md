NEXT: M2 slice 1 (seal) is committed and waiting for owner review. Slice 2: `fragment.yaml` manifest types in `sage-schema`, validation identical native and in WASM, and `sage check <fragment>` (manifest, WIT imports against grants, dry boot with fuel). Slice 3: `sage run --plugin`, port `harness.wander` to a plugin and delete the harness, then `sage.dialogue`.

# Status

| Milestone | State |
|---|---|
| M0 Scaffold | done: workspace, CI (fmt, clippy, test, denylist), ADRs 0001–0004 |
| M1 World model | **closed** 2026-09-16 (ADR 0005-0008; 24 h wall-clock run waived, fast-mode equivalent passed) |
| M2 Plugin seal | in progress: slice 1 done (Wasmtime component host, seal, fuel and memory limits; ADR 0009) |
| M3 Agents | blocked on M2 |
| M4 Client + Foundry MVP | blocked on M3 |
| M5 Workshop + social | blocked on M4 |
| M6 Marketplace | blocked on M5 |

## Gate tests not yet written (they arrive with the code they test)

- An event log from before a *real* schema change replays through its upcaster (M1). The mechanism is tested; this test ships with the first real change.
- Manifest round-trip gives identical results native and in WASM (M2 slice 2)
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

## Open questions for the owner (not blocking M1)

1. Fragment namespace: `creator.slug` or `@creator/slug`?
2. Should agent cards write the Tavern v2 `chara` chunk by default, or only on an explicit Tavern export?
3. Merchant of record when the marketplace arrives: Lemon Squeezy, Paddle or Stripe Connect?
4. Name of the setting-neutral demo world.
5. Should world time pass while the server is down? Currently it doesn't: on restart the clock resumes from the last recorded tick (ADR 0006). The alternative is a catch-up step on boot.
