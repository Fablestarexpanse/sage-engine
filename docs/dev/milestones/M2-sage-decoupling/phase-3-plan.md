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
| 3.4 | Engine seams shop/lodging need: content schema extensions (catalog #7, `api.content.extend`) and plugin admin HTTP routes (#9, `api.http.admin_router`) | done |
| 3.5 | Shop → `plugins/shop` (done: `api.redis`, `api.telemetry`, `api.state.location`, `wallet.pay_later`); lodging → `plugins/lodging` (rent, `lease_sweep` tick job, service for agents) | done |
| 3.6 | Crafting and search → `plugins/crafting`, `plugins/search`; engine progression slots (`progression.skill_used/skill_level`, catalog #3) and `feature` content extensions | done |
| 3.7 | Maestro → `plugins/maestro` (`api.sessions`, `api.entities`, `api.items`, `api.lexicon_keys`) | done |
| 3.8 | Effects API in engine (`api.effects`); hazards → `plugins/hazards` over `RoomEntered` | done |
| 3.9 | Agents → `plugins/agents` (owner ruling); agent wallet reads (`stats["digi"]`, clinic bill, pending takings) move onto `api.wallet`, and the transitional `AgentManager._factions()` service lookup becomes a declared `depends` on `factions` | next |
| 3.10 | Conduit (proficiencies, FRT..PRS, combat resolver, chargen) → `worlds/fablestar/plugins/conduit` | todo |
| 3.11 | Combat, equipment, ambient, effects → first-party plugins (owner G.4) | todo |
| 3.12 | Snapshot contributors; `resonance_levels_total` out of the protocol | todo |
| 3.13 | Declarative client panels; remove Fablestar panels/branding from player-ui | todo |
| 3.14 | Schema: JSONB state, `digi_balance`/`reputation`/`echo_credits` columns (backfill → drop) | todo |
| 3.15 | Redis key namespace by world slug | todo |
| 3.16 | AI slots and style; prompts into `worlds/fablestar/ai` | todo |
| 3.17 | Move Fablestar content into `worlds/fablestar/content`; remove `[transition]` | todo |
| 3.18 | Delete glyph/ship/system/galaxy surfaces and the admin World Builder (owner G.3, G.6) | todo |

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
- **3.4 content extensions.** Rooms, item and entity templates keep unknown YAML fields
  (`extra="allow"`; before this they were silently dropped). A plugin claims one with
  `api.content.extend("room", "shop", ShopModel)` and reads it validated with
  `api.content.extension(room, "room", "shop")`. Invalid blocks log once with the content id and
  read as absent. `ContentExtensions.schemas()` is the hook WorldForge will use for plugin fields.
- **3.4 plugin routes.** Only `api.http.admin_router(router, tool)` exists: mounted at
  `/plugins/<id>/admin/*`, staff token plus an existing Nexus tool id required; `routes` in the
  manifest may only be `"/plugins/<id>/*"`; teardown unmounts. The contract's `play_router` is not
  built until a plugin needs a player-facing HTTP route (prefer-delete / two-world ceiling). Tool
  ids stay the fixed Nexus set until declarative admin panels (3.13) let plugins add nav entries.
- **3.5 shop.** Shop keepers are **character names** in room YAML (`owner: Aldo Vex`), not agent
  persona ids, so the shop plugin needs no agent registry: takings go through
  `wallet.pay_later(owner)` (atomic `wallet_pending:<name>`, banked by the payee's side — today the
  agent tick). The hot-state key was renamed from `digi_pending:`; takings in flight during a
  deploy (seconds) are lost. Admin Shops page now reads `/plugins/shop/admin/shops` and shows the
  world's currency name. `wallet` aliases come from `shop.wallet_aliases` (Fablestar: digi, money).
  Plugin Redis keys must use declared `redis_prefixes`; engine prefixes are reserved.
- **3.6 progression slots.** Plugins report skill use by world-chosen skill ids
  (`api.progression.skill_used(player, skill, chance)`, `skill_level(stats, skill)`); worlds map
  activities to ids in params (`search.skill`, `crafting.skills`, `crafting.deconstruct_skill`).
  The engine's proficiency system provides both slots for every world until it moves into a world
  plugin. Real-run note: field gains were already dead in play (known depth-gate issue), so the
  dev run shows no level change either way; hermetic tests prove the skill ids reach the slot.
- Item `recipe`/`yields`/`scraps` and feature `search` are plugin extensions now; the engine's
  ItemTemplate and FeatureModel no longer define them. `search:{room}:{feature}:finds` keys are the
  search plugin's (`search` is no longer a reserved engine Redis prefix).
- **3.7 maestro.** Flavour text is lexicon: generic defaults in the plugin, Fablestar's station
  lines in its world lexicon. Dread lines are every `maestro.dread.<n>` key, so a world adds lines
  without code. The mercy item is a world param (`maestro.mercy_item`); unset disables mercy.
- **Bisect note:** commit 9a831ea (maestro) does not boot — it was pushed with only the engine
  deletions staged; be48da3 completes it. Skip 9a831ea when bisecting.
- **3.8 hazards.** `RoomEntered` now carries `messages` and is published after arrival bookkeeping,
  so subscriber lines show after the room description. Effects are an engine service key for
  `state.edit`. Resist uses the world's `hazards.resist_skill` through the progression slots.
