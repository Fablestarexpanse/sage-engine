# 0015 — `Occurred` v2 records its audience; memory is a projection of the log

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** the in-memory perception inbox of 0014

## Context

M3 S3a, part 1. Agent memory must be derivable from the log (blueprint §C), and a restarted world's agents must behave exactly like an uninterrupted world's. Who perceives an occurrence depends on where everyone is at that moment. Recomputing that during replay is fragile, because the log doesn't store batch boundaries. It's simpler and exact to record the audience when the occurrence commits.

## Decision

**`Occurred` v2** adds `audience: Vec<EntityId>`, every actor that perceived it, in id order.
- **Filled in by the journal:** `Journal::commit_events` computes each occurrence's audience from the world after the whole batch applies, which is the same moment live deliveries use, stores it, and returns the stored events.
- **Never proposed:** a proposal that already names an audience is refused, so plugins and handlers can't forge who heard something.
- **Deliveries:** built from the stored audience.

**The first real event-schema change.** `Upcasters::core()` registers `Occurred` v1 → v2, which adds an empty audience, because who perceived a v1 occurrence was never recorded. Stored events are never rewritten. All engine and test code now opens logs with `Upcasters::core()`. Plugins that still send v1 occurrence records are upcast on receipt, so existing plugins keep working.

**Gate evidence from a real old build.** `crates/sage-agents/tests/fixtures/log-2a715f3-occurred-v1.db` was recorded by engine build 2a715f3, built from a worktree of that commit: demo-agents with `sage.dialogue`, 600 ticks, 842 events, 378 `Occurred` at v1. It's committed and never regenerated. Tests show:
- it replays through the upcaster to tick 600 with 118 entities, and every old occurrence decodes with an empty audience
- without the upcaster, it's refused with `no upcaster for Occurred v1 -> v2`
- the new engine runs 400 more ticks of agents on top of it, the 378 old events stay at v1, new events are v2, rebuilt memory equals live memory, and genesis replay gives the live snapshot

This closes the M1 gate item deferred in 0005.

**Memories** (`sage_agents::Memories`) are per-actor streams of `(tick, occurred)`, capped at 256 each, oldest dropped first. They're built live from step reports (`observe`) and rebuilt by reading the log (`rebuild`), with identical results (tested). An old occurrence with an empty audience is nobody's memory.

**Scripted `heard` window.** An agent thinking at tick t considers what it perceived in ticks `t - think_every` to `t - 1`. The window depends only on the log and the tick. `sage run` rebuilds memories on start and lets agents think for the first tick it will step, so a restart can't change behaviour.

## Consequences

- A library test restarts a chatty four-agent world every 37 ticks for 1,500 ticks (more than 300 speech lines), and every non-clock event matches an uninterrupted run. With `Memories::rebuild` mutated to return nothing, it fails. The process-level kill -9 test on demo-agents also passes, but that mutation *didn't* fail it: a single kill point rarely lands inside a hearing window. The library test is the real guard. The process test stays as the kill -9 check.
- The scheduler's idle-checkpoint comparison now uses saturating addition. A huge `checkpoint_every` used to overflow once the tick passed zero; the new tests found it.
- Rebuilding memory reads the whole log on start. That's fine at current sizes. S3b's retrieval work, or a memory snapshot, can bound it later.
