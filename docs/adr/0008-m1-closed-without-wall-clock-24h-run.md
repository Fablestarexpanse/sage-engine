# 0008 — M1 closed without the wall-clock 24 h run

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** the "runs 24 h" item of the M1 gate in 0004

## Context

ADR 0004's M1 gate included a 4-place, 100-entity world running for 24 hours of wall-clock time. On 2026-09-16 the owner ruled that there isn't time to wait a day and work must move on.

## Decision

M1 is closed. The 24 h wall-clock run is replaced by evidence already recorded:

- **24 h of world time in fast mode:** 345,600 ticks (24 h at 4 Hz) on the demo world, with 864,324 events. It finished with `refused=0`. `sage inspect` reported `snapshot_matches_replay: true`, tick 345600 and 108 entities, with a 16 MB peak during replay.
- **Kill -9 restart:** `crates/sage-server/tests/restart.rs` checks in CI that a hard-killed and resumed world is byte-identical to one that was never interrupted.
- **Real-time run:** the aborted 24 h run went 6 min 18 s at 4 Hz and was hard-killed at about tick 1,500. Inspect showed tick 1480, 108 entities and `snapshot_matches_replay: true`.

## Consequences

- What fast mode doesn't prove: behaviour tied to wall-clock time over a long run, such as slow memory growth, timer drift, disk growth under `synchronous=FULL`, or OS sleep and clock changes. None of that has been observed. The first long real deployment is where it would show up.
- Future milestone gates that need hours or days of wall-clock time should offer a fast-mode equivalent from the start.
