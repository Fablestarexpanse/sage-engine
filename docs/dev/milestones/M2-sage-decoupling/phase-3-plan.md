# Phase 3 plan: migrate Fablestar out of the engine

**Milestone:** M2 — SAGE engine decoupling · **Branch:** `sage/phase-3` · **Status:** in progress

Living plan. Each step is one or more commits; the game stays playable after every commit
(both world smoke tests green). Order follows `docs/sage/PHASE1_CONTRACTS.md` D.G item 4, amended
by owner G.4 ("every mechanic is a first-party plugin").

## Extraction pattern (applies to every step)

1. Keep the *generic* part in the engine as a service or event (counters, wallet, effects API…).
2. Move the *rule* into `plugins/<id>/` (first-party, reusable) or `worlds/fablestar/plugins/<id>/`
   (Fablestar-only), registering only through `sage.api`.
3. Engine call sites stop importing the subsystem: they call the service or publish an event, and
   send back whatever lines subscribers add (`event.messages`).
4. Fablestar enables the plugin in `world.toml`; Rivermoot does not unless it needs it.
5. Tests move with the code (`engine/tests/plugins/test_<id>.py`, loaded through `PluginHost`).
6. Ratchet counts must drop; update the baseline in the same commit.

## Steps

| # | Step | Status |
|---|------|--------|
| 3.1 | Counters service + `CountersChanged` event; achievements → `plugins/achievements` | done |
| 3.2 | Factions + missions → `plugins/factions` (subscribe to `EntityKilled`) | in progress |
| 3.3 | Wallet service (world currencies) + shop and lodging → `plugins/shop`, `plugins/lodging` | todo |
| 3.4 | Crafting and search → `plugins/crafting`, `plugins/search` | todo |
| 3.5 | Maestro → `plugins/maestro` | todo |
| 3.6 | Effects API in engine; hazards → `plugins/hazards` | todo |
| 3.7 | Agents → `plugins/agents` (owner ruling) | todo |
| 3.8 | Conduit (proficiencies, FRT..PRS, combat resolver, chargen) → `worlds/fablestar/plugins/conduit` | todo |
| 3.9 | Combat, equipment, ambient, effects → first-party plugins (owner G.4) | todo |
| 3.10 | Snapshot contributors; `resonance_levels_total` out of the protocol | todo |
| 3.11 | Declarative client panels; remove Fablestar panels/branding from player-ui | todo |
| 3.12 | Schema: JSONB state, `digi_balance`/`reputation`/`echo_credits` columns (backfill → drop) | todo |
| 3.13 | Redis key namespace by world slug | todo |
| 3.14 | AI slots and style; prompts into `worlds/fablestar/ai` | todo |
| 3.15 | Move Fablestar content into `worlds/fablestar/content`; remove `[transition]` | todo |
| 3.16 | Delete glyph/ship/system/galaxy surfaces and the admin World Builder (owner G.3, G.6) | todo |
