NEXT: M0 scaffold is pushed and waiting for owner review. The next step, once approved, is the first M1 slice: add `bevy_ecs` to sage-core and `rusqlite` to sage-store, build an `events` table with `schema_version`, a snapshot table, and a replay test.

# Status

| Milestone | State |
|---|---|
| M0 Scaffold | done: workspace, CI (fmt, clippy, test, denylist), ADRs 0001–0004 |
| M1 World model | not started |
| M2 Plugin seal | blocked on M1 |
| M3 Agents | blocked on M2 |
| M4 Client + Foundry MVP | blocked on M3 |
| M5 Workshop + social | blocked on M4 |
| M6 Marketplace | blocked on M5 |

## Gate tests not yet written (they arrive with the code they test)

- Replay reproduces the snapshot byte for byte (M1)
- An event log from before a schema change replays through an upcaster (M1)
- Every stored event carries `schema_version` (M1)
- A plugin importing an undeclared WIT interface fails at boot (M2)
- Manifest round-trip gives identical results native and in WASM (M2)
- The PNG chunk parser is fuzzed (whenever the parser exists)
- The demo world plays with every AI driver disabled (M3)

## Open questions for the owner (not blocking M1)

1. Fragment namespace: `creator.slug` or `@creator/slug`?
2. Should agent cards write the Tavern v2 `chara` chunk by default, or only on an explicit Tavern export?
3. Merchant of record when the marketplace arrives: Lemon Squeezy, Paddle or Stripe Connect?
4. Name of the setting-neutral demo world.
