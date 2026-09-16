# 0007 — `sage run`, seed files, and the restart gate

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

The M1 gate needs a world that actually runs: a fixed tick rate, periodic snapshots, survival of a hard kill, and a 24-hour run. It also needs content to run, before M2 defines fragment manifests.

## Decision

**`sage run <world.db>`** opens one SQLite file and steps the scheduler at `--hz` (default 4; 0 means as fast as possible). It sleeps against a deadline so the rate doesn't drift, and resyncs instead of bursting if it falls more than 10 ticks behind. It saves a snapshot every `--snapshot-every` ticks. It stops cleanly on Ctrl-C or at `--until-tick`: it records the final tick with `Scheduler::record_clock`, then saves a snapshot. A log failure exits non-zero without writing a snapshot. No async runtime yet; that arrives with the network transport at M4.

**`sage inspect <world.db>`** opens the world twice, once from the newest snapshot plus the log tail and once from genesis. It prints tick, sequence, entity count and whether the two agree, and exits non-zero if they don't. Run it after any long or interrupted run.

**Seed files (interim).** `--seed <file>` fills a *new* world from `{"schema": "sage.seed/1", "entities": [...]}`, where each entity uses the snapshot entity shape. The seed is applied through `entities_to_events` and committed as ordinary events, so it passes every world rule. A world that already has a history refuses a seed. This format covers M1 only. M2 content fragments with manifests replace it, and `sage.seed/1` either becomes an import path or is dropped by ADR.

**Demo world.** `worlds/demo/seed.json` has four places joined by a one-way ring of `onward` links and 100 markers spread among them: 108 entities, with no setting. It's data, not code.

**Test harness system.** `harness.wander` in `sage-server` moves located entities along the first link out of their place every N ticks. It's off unless `--wander-every` is set. It exists only so M1 runs have deterministic activity. It is behaviour, and behaviour belongs in code fragments, so it's deleted once M2 can load an equivalent plugin.

## Consequences

- **Restart gate (tested):** `crates/sage-server/tests/restart.rs` runs the demo world to tick 20,000 uninterrupted. It runs a second copy, hard-kills the process (`Child::kill`: SIGKILL, or TerminateProcess on Windows) after tick 3,000 is in the log, and resumes it to tick 20,000. Both logs replay to byte-identical snapshots. Mutation check: making appends non-atomic (one transaction per event) fails this test in 3 of 3 runs.
- A clean Ctrl-C shutdown has no automated test; it follows the same code path as `--until-tick`.
- The 24-hour run is a manual gate run, not CI. Record its result in DECISIONS.
