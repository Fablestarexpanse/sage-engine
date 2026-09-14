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
| 3.11 | Combat, equipment, ambient, effects → first-party plugins (owner G.4): ambient, effects, combat, equipment, consumables (`use`) | done |
| 3.12 | Snapshot contributors (`api.snapshot.contribute`); `resonance_levels_total` out of the protocol | done |
| 3.13 | Declarative client panels; remove Fablestar panels/branding from player-ui: 3.13a API + renderer, 3.13b Conduit panels, 3.13c mock panels and branding out; 3.13d deferred until an admin panel is needed | done |
| 3.14 | Schema: JSONB state, `digi_balance`/`reputation`/`echo_credits` columns, retire `agent_state` (backfill → drop) | done |
| 3.15 | Redis key namespace by world slug | done |
| 3.16 | AI slots and style; prompts into `worlds/fablestar/ai`: 3.16a slots + prompts moved, 3.16b style done | in progress |
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
- **3.11 combat, equipment, consumables (done).** One commit for combat, equipment and consumables because combat reads
  gear bonuses and ammo: `plugins/equipment` (item.slot/attack/defense/ammo extensions, equip/
  unequip/gear, service bonuses/fire/equip — agents switch from api.equipment to it),
  `plugins/consumables` (item.heal, `use`, service for agents), `plugins/combat` (attack/flee,
  combat.skills param, narration via an engine AI call, EntityKilled). Engine keeps entity locks
  (move out of commands/combat.py into the spawner) and gains `[touches].stats_keys` so a plugin
  may declare engine-owned stats it writes (combat and consumables write `hp`). Rivermoot must
  enable combat (its levels plugin listens for kills). Engine combat tests (test_commands,
  test_death, test_combat_narration, test_equipment) move to plugin host tests.
  As built: new engine API pieces are `state.relocate`, `entities.save/lock/kill`,
  `characters.record_death` and `ai.narrate(template, max_tokens, **vars)`; `api.equipment` and the
  ItemTemplate `heal/slot/attack/defense/ammo` fields are gone (extensions now). Behaviour changes:
  `inventory` no longer lists worn gear and lost its `equipment`/`gear` aliases (the equipment
  plugin's `gear` command shows it); `examine <player>` no longer names their weapon (the engine does
  not read a plugin's state block); ammo is checked for every worn ammo-fed item, not only `weapon`.
  World param `engine.combat.skills` became `combat.skills`; `combat.flee_chance` (0.5) and
  `combat.narration_template` are optional. Rivermoot enables combat without equipment. Agents use
  the equipment/consumables services when those plugins are enabled (optional depends).
- **3.13 plan (declarative panels).** Four commits, each playable:
  - 3.13a engine + generic client renderer. `api.ui.panel(name, kind, section, icon="")` registers
    player panel `<plugin>.<name>`, titled by lexicon `<plugin>.panel.<name>`, whose data is one of
    the plugin's own snapshot sections; `[touches].panels` seals it. Kinds `stat_sheet`, `wallet`,
    `tree`, `list`, `key_value`, `table`; `module` is refused at boot as unsupported in this engine
    version (DECISIONS G.10). The character snapshot gains `panels` (specs with resolved titles);
    player-ui renders each kind generically and lists declared panels in the panel toggles. Data
    shapes are documented in `sage/network/panels.py`; a tree node may carry `actions`
    (`{label, command}`), sent as typed commands, so panels gain no authority commands lack.
    First users: factions (`list`), equipment (`key_value`), Rivermoot levels (`stat_sheet`).
  - 3.13b Conduit declares its sheet (`stat_sheet`) and skill tree (`tree` with raise/lower/lock
    actions); the Conduit strip and ProficienciesPanel leave player-ui.
    As built: the tree lists every domain plus the leaves a character has touched (level > 0 or a
    state other than raise), not all 278 leaves, because sections ride on every snapshot push;
    browsing untouched leaves is the `prof`/`bonus` commands' job. The generic Character panel
    keeps name, portrait, account, wallet chip, PvP, reputation, location, the progression
    `levels_total` ("Level") and health; Mana/Madness placeholders and the FRT..PRS/STR/DEX tab are
    gone. `resonanceLevelsTotal` became `levelsTotal` in the client. Showing a panel from the
    toggles now brings it to the front.
  - 3.13c player-ui loses mock panels (glyphs, quests, target, session stats, keybinds, triggers,
    quick actions: owner G.3 "mock client panels") and Fablestar branding (header from world name,
    wallet chip from the world's primary currency).
    As built: public `GET /play/world` ({id, name}) titles the page, the sign-in header and the
    play header (`WorldContext`); the player theme's `glyph` palette became `hue`
    (`border.glyph` -> `border.accent`, `text.glyph` -> `text.accentStrong`). Left for later
    steps, because they are wire or schema names: `digi_balance`/`echo_credits` and the pixel/digi
    chips (3.14 schema), the chargen skill picker (Conduit-shaped; needs a generic chargen
    options renderer), and the `glyph_cast` narrative type and glyph entity kind (3.18 deletions).
  - 3.13d admin surface (`surface="admin"`, source = the plugin's admin route) only if an admin
    panel is needed by then; the existing plugin admin tabs keep working through their routes.
  `schema_form` waits for its first user (two-world ceiling).
- **3.14 plan (schema).** Each column change is backfill-then-drop across commits; drops come last
  so any step before them can be rolled back with `db downgrade`.
  - 3.14a (done) core `o8p9q0r1s2t3`: `characters.stats`/`inventory` JSON → JSONB (reversible
    cast); `agent_state` renamed `retired_agent_state` (`agents0001` copies from either name,
    proven by a live test that runs core head first); ORM `Character.room_id` loses its
    Fablestar default (every insert already passes the world's start room); plugin uninstall
    purges `characters` only.
  - 3.14b (done) core `p9q0r1s2t3u4` copies the column into `stats[<primary currency key>]` for
    every row (the column was the login-time truth) and downgrade copies it back; the key comes
    from the configured world (one DB per world). Engine code no longer reads or writes the
    column: login, respawn bill, flush and new characters use the wallet over stats, and clients
    get an engine `wallet` snapshot section `{key, label, amount}` in both the character list and
    live snapshots (the chip now updates after a purchase). The admin editor's separate "Digi"
    field is gone; balances are edited in the stats JSON under the currency key. The migration
    must name the legacy column once, so its file is the one new ratchet entry (1 hit; see
    DECISIONS).
  - 3.14c-1 (done) core `q0r1s2t3u4v5` renames the account column to `ai_credits`
    (reversible). Wire, admin API, notices (`ai_credits_granted`), config (`starting_ai_credits`,
    `credits_per_usd`; the old comfyui.toml names load for one release with a warning) and both
    clients use the engine name; the art currency's default display name is "credits" (a
    deployment still sets its own label, e.g. "pixels", in comfyui.toml). The hardcoded USD
    bundles in the admin tab stay for now (contracts: move to deployment config).
  - 3.14c-2 (done) Fablestar world plugin `morality` (state block `morality.standing`, -100..100,
    a ranged `stat_sheet` panel titled "Morality" with a band note). Branch `plg_morality`
    (`morality0001`, no tables) copies `characters.reputation` into the block and zeroes the
    column; downgrade copies back. The engine API, admin editor and player-ui no longer carry
    reputation; `ReputationThermometer` is deleted. `stat_sheet` rows gained optional `min`.
    Standing is edited through the stats JSON; nothing in play changes it yet.
  - 3.14d (done) core `r1s2t3u4v5w6` drops `characters.digi_balance`, `characters.reputation`
    and `retired_agent_state`, refusing while any row still has a non-zero standing column (a
    world plugin that owns it has not migrated). Downgrade re-creates them empty; the earlier
    downgrades (p9q0r1s2t3u4, plg_morality) then copy the values back from stats, so the door is
    one-way only for the retired agent rows, which live in `plg_agents_state`. Live tests that
    need the old schema downgrade to `q0r1s2t3u4v5` first. Dev DB backups: scratchpad `devdb_before_314a/b/c1/c2.sql`; take a fresh
    one before 3.14d.
- **3.15 Redis namespace (done).** `RedisState(config, namespace=world.id)`: every engine key is
  stored as `<world id>:<logical key>` (`fablestar:player:Hero:stats`). Code that builds keys
  outside the typed accessors goes through `redis.key()` / `redis.unkey()`: telemetry heatmaps,
  wallet pending takings, the litter sweep scan, the admin world-live scan and every plugin
  `api.redis` call (plugins still declare and use logical keys; the namespace is added under
  them). On boot, keys under the engine's reserved prefixes and the enabled plugins'
  `redis_prefixes` that were written before namespacing are renamed into the namespace
  (`RENAMENX`, never over an existing key), so Redis-only state such as lodging leases and shop
  stock survives the upgrade; the step is a no-op afterwards. Caveat: on a Redis shared by
  several worlds, the first world to boot adopts all pre-namespace keys, which only exist from
  single-world deployments. Test fakes keep an empty namespace.
- **3.16 plan (AI slots and style).**
  - 3.16a (done) `sage.llm.prompts`: engine slots `narrate.room`, `forge.room`, `forge.content`,
    `image.area`, `image.portrait`, `image.scene`; plugins declare `<plugin>.<name>` with
    `api.ai.slot(name)` (sealed by `[touches].ai_slots`) and render with `api.ai.narrate(name)`;
    `api.ai.enabled(name)` lets callers skip AI work. A world fills a slot with
    `ai/prompts/<slot>.j2`; rendering an empty or undeclared slot raises `SlotDisabled` instead of
    the old "Error: Could not render prompt" string that was sent to the LLM. Callers: `look` skips
    the narration task, forge routes answer 503 `ai_slot_disabled`, image-prompt suggestions return
    `{"error": "ai_slot_disabled"}`, combat sends no prose. The seven templates moved from the
    repository `prompts/` to `worlds/fablestar/ai/prompts/` under slot names
    (`combat_narration` -> `combat.narration`, `room_description` -> `narrate.room`, ...);
    `[transition] prompts_dir` is gone. Rivermoot ships no templates and runs with every slot
    disabled.
  - 3.16b (done) `sage.llm.style`: optional `ai/style.yaml` with `tone`, `system_prompt`,
    `image.style`/`image.negative` and `content_rules`. Every slot template sees `style`; the LLM
    client's default system prompt comes from it (no more "dark sci-fi MUD" default); the room
    narration validator uses its rules (engine golden-rule regexes when absent) and a rejected
    narration is dropped instead of becoming "[The narration becomes garbled by static...]".
    `LLMClient.generate()` and its in-fiction fallback strings are deleted (the one caller, the
    Nexus test completion, reports the error). The server watches the world's `ai/` dir, so style
    edits hot-reload. Fablestar's templates read their tone and image style from its style file.
    The image-prompt jobs keep their generic engine system prompts ("output only a single
    image-generation prompt"). `image.negative` has no consumer until 3.16c.
  - 3.16c ComfyUI graphs into `ai/comfyui/<role>.json` with `ai/loras.yaml`; config paths stay as
    deployment overrides.
  - Versioned prompt/style edits in Nexus (B.6 overrides) wait for a user of them (two-world
    ceiling); package files stay the source.

