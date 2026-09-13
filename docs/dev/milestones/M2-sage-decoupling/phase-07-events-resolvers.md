# Phase 07: Event bus, resolver slots, tick jobs

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** phase-05
**Tags:** language=python, kind=feature, size=m

## Goal

Contracts D.B: fan-out notifications go through a real event bus; single-answer decisions go
through typed resolver slots with engine defaults. This gives Phase 3 the seams to move
achievements, factions, missions and Fablestar's death rules out of engine code without
changing behaviour, and gives the plugin loader something to register against.

## Spec (as built)

1. `sage.core.events`: `EventBus` (exact type, subscription order, awaited, per-subscriber
   error logging with owner, `unsubscribe_owner`), `emit(server, event)`; events
   `CommandExecuted`, `RoomEntered`, `EntityKilled` (mutable `stats`, `messages`),
   `PlayerDied`, `SessionStarted`, `SessionEnded`.
2. Published from: dispatcher (after a successful handler), movement, combat kills (subscriber
   messages are sent with the kill lines), `record_player_death` (every death cause), session
   bootstrap and teardown.
3. `sage.core.resolvers.Resolvers`: `define`/`provide`/`withdraw`/`get`/`owner`; a second
   provider is an error. Engine slots `death.check`, `death.respawn` (`sage.world.death`):
   respawn room from the world, `engine.death.respawn_hp_fraction` (0.5) and
   `engine.death.respawn_bill_max` (0) world params. Fablestar sets the bill to 10, preserving
   its clinic charge; the engine no longer hardcodes it.
4. `TickManager.every(seconds, job, name)` and `unregister`. `WorldPackage.param`.

## Update Log

### Update — 2026-09-13 (complete)

410 passed + 5 skipped (9 bus/resolver/tick/death tests, 1 kill+move event integration test).
Real server: movement round-trip fine with events on. The run surfaced a pre-existing tick
crash (`AmbientManager.on_tick` iterating the live session dict across an await) — fixed in
its own commit `e618da2` with a regression test.
