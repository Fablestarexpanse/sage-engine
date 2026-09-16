# 0005 — Event log, snapshot format and the single mutation path

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M1 needs a log that is the only source of truth, snapshots that replay to identical bytes, and versioning on everything persisted (blueprint §D2). v1 lost edits because two stores disagreed.

## Decision

**One way to change a world.** `sage_core::Journal::commit(tick, events)` checks the whole batch against the current world, appends it to the `EventLog` in one transaction, then applies it. `World` has no public mutating methods. If the check or the append fails, neither the log nor the world changes. On open, the journal restores the newest snapshot and replays every later event through the same check and apply code.

**Events.** Stored as `(seq, tick, event_type, schema_version, payload JSON)`. `seq` starts at 1 and has no gaps. An append names its first `seq` and is refused if the log has moved on, so a second writer cannot interleave. Old payloads are upcast on read by registered `Upcasters`, one version at a time. A payload from a newer engine is refused, never guessed at. Core events: `EntityCreated`, `EntityDestroyed`, `ComponentSet`, `ComponentRemoved`, all at v1.

**Components.** Every component has a stable name (`sage.describable`) and a version. `ComponentSet` carries the component version. A world refuses unregistered components, a version that differs from the registered one, and data that doesn't deserialize. Core components are `sage.describable`, `sage.place` and `sage.located`.

**Entity ids.** Stable `u64` ids that are never reused, not even after a destroy. They are separate from `bevy_ecs` entity handles, which never reach disk.

**Snapshots.** Canonical JSON: format version, `last_seq`, `tick`, `next_entity_id`, entities sorted by id, components sorted by name, object keys sorted. Restoring checks every component the same way an event is checked.

**SQLite.** WAL mode with `synchronous=FULL`. The tables are `STRICT`. CHECK constraints refuse `schema_version <= 0` and invalid JSON. Triggers refuse `UPDATE` and `DELETE` on `events`. The store's own schema version lives in `PRAGMA user_version`, and a file from a newer engine is refused.

## Consequences

- Replaying from genesis, and restoring a snapshot then replaying the tail, both reproduce the live snapshot byte for byte. Both are tested over a 4-place, 100-entity world with 200 ticks of changes.
- The upcaster mechanism is tested, but on a fixture event type. The gate item "a log written before a real event-schema change replays through its upcaster" stays open until the first real change happens. That change must ship with that test.
- `read_from` loads the whole tail into memory. That's fine for M1 sizes; switch to streaming before the 24-hour run if memory says so.
- Component data migrations (a component changing version) are not built yet. Today a version mismatch is refused.
