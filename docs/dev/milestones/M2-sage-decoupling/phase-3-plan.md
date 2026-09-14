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
| 3.9 | Agents → `plugins/agents` (owner ruling); agent wallet reads (`stats["digi"]`, clinic bill, pending takings) move onto `api.wallet`, and the transitional `AgentManager._factions()` service lookup becomes a declared `depends` on `factions` | done |
| 3.10 | Conduit (proficiencies, FRT..PRS, combat ratings, chargen) → `worlds/fablestar/plugins/conduit` | done |
| 3.11 | Combat, equipment, ambient, effects → first-party plugins (owner G.4): ambient and effects done; combat + equipment + consumables (`use`) next | in progress |
| 3.12 | Snapshot contributors (`api.snapshot.contribute`); `resonance_levels_total` out of the protocol | done |
| 3.13 | Declarative client panels; remove Fablestar panels/branding from player-ui | todo |
| 3.14 | Schema: JSONB state, `digi_balance`/`reputation`/`echo_credits` columns, retire `agent_state` (backfill → drop) | todo |
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
- **3.9 agents, open question (one-way door).** Agents persist in the engine table `agent_state`.
  A plugin may only own `plg_agents_*` tables, so either (a) the agents plugin gets
  `plg_agents_state` with a backfill-then-drop migration of `agent_state`, or (b) the engine
  persists accountless characters (agents become `characters` rows with no account) and the plugin
  owns no table. Asked the owner before building. Also to move with agents: Fablestar-specific life
  goals (food item, clinic bill, evening pub room, pub small-talk prompt) become world params and
  AI slots; persona attributes go through a chargen seed slot instead of writing Conduit blocks.
- **3.9 agents plugin.** `plugins/agents` owns personas (`content/agents`), the Body/Brain, the
  `agents` tick job, `plg_agents_state` (branch `plg_agents`, backfilled from `agent_state`), the
  admin routes at `/plugins/agents/admin/*` (agents, statboard, heatmaps, persona) and a name claim
  so players can't take agent names. Optional dependencies on factions/shop/lodging/search. World
  params give the life-goal vocabulary (`agents.food_item`, `forage_item`, `social_zones`,
  `evening_room`); prompts are `agents.prompt.*` lexicon (Fablestar overrides setting and notes).
  Death uses the world's `death.respawn` policy and wallet bill instead of a hardcoded clinic bill.
  Persona YAML's starting wallet key is `money:`. The world smoke test now runs
  `python -m sage db upgrade` per world in its own database (one DB per world).
- **Retiring `agent_state` (3.14, order-safe).** Alembic may run a core revision before a plugin
  branch's revision in one `upgrade heads`, so the core step must not drop `agent_state` while
  `plg_agents` could still need to copy from it. Plan: core renames it to `retired_agent_state`;
  `agents0001` is amended to copy from whichever of the two exists; a later core revision drops the
  retired table. The engine `AgentState` model stays until then (migration drift test), and
  `sage plugin uninstall --purge-state` only purges `characters` rows for plugin blocks — a plugin
  that stores its own characters (agents) purges on restart.
- **3.12 order.** Done before Conduit (3.10) because Conduit's client data has to leave through
  a snapshot section. The snapshot and the character list now carry `sections`; the engine's own
  `progression` section is `{levels_total}` from the progression slot. The player client reads it
  from there (its panels still say Resonance until 3.13).
- **3.10 Conduit.** The whole proficiency package, the `score/prof/cap/bonus/raise/lower/lock`
  commands, catalog build scripts and their tests live in `worlds/fablestar/plugins/conduit`
  (world-private, proprietary per NOTICE — no longer under the engine's FSL paths). It provides
  every progression, chargen and `combat.ratings` slot; the engine's temporary providers are gone,
  so a world without such a plugin runs on the slot defaults (Rivermoot). New engine pieces:
  `chargen.options` behind public `GET /play/chargen/options` (the player client's skill picker
  reads it, no plugin id in the client), `/plugins/conduit/admin/catalog` for the admin Skills page.
  `server.proficiency_combat_hybrid` config became the world param `conduit.combat_hybrid`. World
  plugin tests run with the suite (`pytest.ini` testpaths include `worlds`).
- **3.11 remaining plan.** One commit for combat, equipment and consumables because combat reads
  gear bonuses and ammo: `plugins/equipment` (item.slot/attack/defense/ammo extensions, equip/
  unequip/gear, service bonuses/fire/equip — agents switch from api.equipment to it),
  `plugins/consumables` (item.heal, `use`, service for agents), `plugins/combat` (attack/flee,
  combat.skills param, narration via an engine AI call, EntityKilled). Engine keeps entity locks
  (move out of commands/combat.py into the spawner) and gains `[touches].stats_keys` so a plugin
  may declare engine-owned stats it writes (combat and consumables write `hp`). Rivermoot must
  enable combat (its levels plugin listens for kills). Engine combat tests (test_commands,
  test_death, test_combat_narration, test_equipment) move to plugin host tests.
