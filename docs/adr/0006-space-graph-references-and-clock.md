# 0006 — Space graph, reference rules, apply-with-undo, world clock

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** the commit order in 0005 ("check the batch, append, then apply")

## Context

M1 needs a space graph and a clock. The space graph brings rules that depend on world state: a link can't point at a missing place, a container can't be destroyed while something is inside it, and containment can't loop. ADR 0005 checked a batch against a lightweight overlay before applying it. Doing that for reference and cycle rules would mean a second copy of every rule that reads component values, and two copies can drift apart.

## Decision

**Apply with undo.** `World::apply_batch` applies events for real, one at a time, and each step records how to undo itself. If an event is refused, the steps are undone in reverse. `Journal::commit` applies the batch, then appends it to the log, and undoes the batch if the append fails. The world and the log still change together or not at all. Each rule is written once, against real state. Snapshot restore applies the snapshot as events, so it enforces the same rules.

**Space graph.** `sage.link` (v1) is a component on its own entity: `{from, to, label}`, one-way. A two-way passage is two links. A link lives on its own entity so doors, locks and costs can be fragment components on it later. The engine only matches the label; player-facing wording belongs to the world. Links aren't restricted to `sage.place` entities, so a vehicle or a container can have links too. Queries: `contents`, `containers`, `links_from`, `links_to`, `link_named`. Every query returns results in sorted order.

**Reference rules.** `Component::references()` names the entities a component points at. `sage.located` and `sage.link` declare theirs. A world refuses:
- setting a component whose references aren't live entities
- destroying an entity that another entity still references
- placing an entity inside itself, or inside anything it contains
- a batch whose tick is earlier than the world's tick

**Clock.** `Scheduler::step` advances one tick and runs systems in the order they were added. Each system sees the commits of the systems before it in that tick. A refused system batch is reported and the other systems still run; only a log failure stops the step. While the world is idle, a `ClockAdvanced` event is recorded every `checkpoint_every` ticks. On restart, the clock resumes from the last tick in the log.

## Consequences

- A crash loses at most `checkpoint_every` ticks of idle world time. At 4 Hz with a checkpoint every 240 ticks, that's one minute, and 1,440 events a day on an idle world.
- **World time does not advance while the server is down.** This is a gameplay choice the owner may want to reverse (see STATUS open questions). Reversing it would mean a catch-up step on boot, not a change to the log.
- The destroy check and the space queries scan every entity. That's fine at M1 sizes. Add reverse indexes when profiling shows the need.
- A crash between two systems' commits in the same tick leaves the later systems unrun for that tick. On restart, the clock resumes at that tick and moves on, so those systems skip it. Revisit this if a system needs exactly-once runs per tick.
