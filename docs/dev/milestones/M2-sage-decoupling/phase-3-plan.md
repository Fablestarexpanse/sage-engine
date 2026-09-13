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
| 3.2 | Wallet service over world currencies (`sage.world.wallet`, `api.wallet`); shop, lodging, mission pay, respawn bill, new-character balance use it | done |
| 3.3 | Factions + missions → `plugins/factions` (subscribe to `EntityKilled`); `PluginAPI` gains `counters`, `inventory`, `content.cached`, `state.edit` | done |
| 3.4 | Shop and lodging → `plugins/shop`, `plugins/lodging` | next |
| 3.5 | Crafting and search → `plugins/crafting`, `plugins/search` | todo |
| 3.6 | Maestro → `plugins/maestro` | todo |
| 3.7 | Effects API in engine; hazards → `plugins/hazards` | todo |
| 3.8 | Agents → `plugins/agents` (owner ruling); agent wallet reads (`stats["digi"]`, clinic bill, pending takings) move onto `api.wallet`, and the transitional `AgentManager._factions()` service lookup becomes a declared `depends` on `factions` | todo |
| 3.9 | Conduit (proficiencies, FRT..PRS, combat resolver, chargen) → `worlds/fablestar/plugins/conduit` | todo |
| 3.10 | Combat, equipment, ambient, effects → first-party plugins (owner G.4) | todo |
| 3.11 | Snapshot contributors; `resonance_levels_total` out of the protocol | todo |
| 3.12 | Declarative client panels; remove Fablestar panels/branding from player-ui | todo |
| 3.13 | Schema: JSONB state, `digi_balance`/`reputation`/`echo_credits` columns (backfill → drop) | todo |
| 3.14 | Redis key namespace by world slug | todo |
| 3.15 | AI slots and style; prompts into `worlds/fablestar/ai` | todo |
| 3.16 | Move Fablestar content into `worlds/fablestar/content`; remove `[transition]` | todo |
| 3.17 | Delete glyph/ship/system/galaxy surfaces and the admin World Builder (owner G.3, G.6) | todo |

## Notes

- **3.2 order change.** Mission payouts and shop/lodging all move money, so the wallet had to become
  an engine service before any of them could become plugins; otherwise the factions plugin would
  hardcode Fablestar's currency key. Wallet came first, factions follow.
- **Wallet storage until the schema step.** Balances live in the stats blob under the currency key.
  The primary balance is still mirrored to the legacy `characters.digi_balance` column on login and
  flush; for Rivermoot that column holds silver. The column is renamed/dropped in the schema step.
- `server.game_currency_display_name` and `server.starting_digi_balance` were deleted from config:
  the name comes from the world lexicon (`currency.<key>.name`) and the starting balance from
  `currencies.yaml`. Old keys in a deployment's `server.toml` are ignored.
- **3.3 new plugin surfaces.** Moving missions out needed four engine seams, all generic:
  `api.counters.count` (bump + `CountersChanged`), `api.inventory.get/set`,
  `api.content.cached(subdir, loader)` (mtime-reloading `DirCache`; achievements uses it too), and
  `api.state.edit(player_id)` — a whole-character edit for work spanning the plugin's own blocks and
  engine services. `edit` works on a copy and refuses (saving nothing) if any other top-level key
  changed, so a plugin still cannot write vitals or another world's progression data.
- Standing names (`loathed` … `exalted`) are ids; players see `factions.standing.<id>` from the
  lexicon.
