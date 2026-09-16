NEXT: M1 slice 1 (event log + projection) is committed and waiting for owner review. Slice 2 is the space graph (`Link` component, containment queries) plus a world clock/scheduler with a fixed tick. Slice 3 is a `sage run` loop and the kill -9 / 24 h gate runs.

# Status

| Milestone | State |
|---|---|
| M0 Scaffold | done: workspace, CI (fmt, clippy, test, denylist), ADRs 0001–0004 |
| M1 World model | in progress: slice 1 done (Journal, SQLite log, snapshots, replay tests; ADR 0005) |
| M2 Plugin seal | blocked on M1 |
| M3 Agents | blocked on M2 |
| M4 Client + Foundry MVP | blocked on M3 |
| M5 Workshop + social | blocked on M4 |
| M6 Marketplace | blocked on M5 |

## Gate tests not yet written (they arrive with the code they test)

- An event log from before a *real* schema change replays through its upcaster (M1). The mechanism is tested; this test ships with the first real change.
- A 4-place, 100-entity world runs for 24 h (M1, needs the run loop)
- After kill -9, restart rebuilds state from the log (M1, needs the run loop)
- A plugin importing an undeclared WIT interface fails at boot (M2)
- Manifest round-trip gives identical results native and in WASM (M2)
- The PNG chunk parser is fuzzed (whenever the parser exists)
- The demo world plays with every AI driver disabled (M3)

## Gate tests passing

- Replay from genesis reproduces the live snapshot byte for byte (`crates/sage-store/tests/replay.rs`)
- Restoring a snapshot then replaying the tail gives the same bytes
- The database refuses events with no schema version, and refuses edits or deletes on events
- A refused batch writes nothing; a second writer is refused
- A log or store written by a newer engine is refused

## Open questions for the owner (not blocking M1)

1. Fragment namespace: `creator.slug` or `@creator/slug`?
2. Should agent cards write the Tavern v2 `chara` chunk by default, or only on an explicit Tavern export?
3. Merchant of record when the marketplace arrives: Lemon Squeezy, Paddle or Stripe Connect?
4. Name of the setting-neutral demo world.
