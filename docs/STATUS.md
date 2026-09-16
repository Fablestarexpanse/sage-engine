NEXT: M1 slice 3 (`sage run`, `sage inspect`, demo seed, kill -9 restart test; ADR 0007) is committed and waiting for owner review. The last open M1 gate is the 24 h run. Start it with the command under "24 h gate run" below, then run `sage inspect` on the file and record the result in DECISIONS.md. After that, M1 closes and M2 (plugin seal) can begin.

# Status

| Milestone | State |
|---|---|
| M0 Scaffold | done: workspace, CI (fmt, clippy, test, denylist), ADRs 0001–0004 |
| M1 World model | in progress: slices 1-3 done (event log, snapshots, space graph, clock, run loop, restart gate; ADR 0005-0007); only the 24 h run remains |
| M2 Plugin seal | blocked on M1 |
| M3 Agents | blocked on M2 |
| M4 Client + Foundry MVP | blocked on M3 |
| M5 Workshop + social | blocked on M4 |
| M6 Marketplace | blocked on M5 |

## Gate tests not yet written (they arrive with the code they test)

- An event log from before a *real* schema change replays through its upcaster (M1). The mechanism is tested; this test ships with the first real change.
- A 4-place, 100-entity world runs for 24 h (M1, manual run; see below)
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
- Space graph and containment: dangling references, destroying a referenced entity, containment cycles and ticks going backwards are all refused, and a refusal mid-batch leaves the world byte-identical
- A failed log append undoes the world change
- A scheduled world (a system moving entities along links, plus idle checkpoints) replays byte-identically and resumes its clock from the log

- A demo world hard-killed mid-run and resumed ends byte-identical to an uninterrupted run (`crates/sage-server/tests/restart.rs`)
- `--seed` is refused on a world that already has a history

## 24 h gate run

```bash
cargo build --release -p sage-server
target/release/sage run m1-24h.db --seed worlds/demo/seed.json --wander-every 40 --until-tick 345600
target/release/sage inspect m1-24h.db
```

345,600 ticks at 4 Hz is 24 h. Pass criteria: the run exits 0 with `refused=0`, and `inspect` prints `"snapshot_matches_replay":true`, `"tick":345600` and `"entities":108`.

## Open questions for the owner (not blocking M1)

1. Fragment namespace: `creator.slug` or `@creator/slug`?
2. Should agent cards write the Tavern v2 `chara` chunk by default, or only on an explicit Tavern export?
3. Merchant of record when the marketplace arrives: Lemon Squeezy, Paddle or Stripe Connect?
4. Name of the setting-neutral demo world.
5. Should world time pass while the server is down? Currently it doesn't: on restart the clock resumes from the last recorded tick (ADR 0006). The alternative is a catch-up step on boot.
