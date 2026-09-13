# SAGE Phase 0 — Audit of Fablestar-specific code, content, tools and docs

**Date:** 2026-09-13 · **Branch:** `sage/phase-0-1` · **Brief:** `docs/sage/BRIEF.md` ·
**Rulings log:** `docs/sage/DECISIONS.md` · **Next deliverable:** `docs/sage/PHASE1_CONTRACTS.md`

This is the inventory the brief asks for in §5 Phase 0. It changes no code. Line numbers are
1-based and were read from the tree at commit `dbfdcc8`. Paths are relative to the repo root;
`src/fablestar/` is abbreviated to `sf/` in the tables.

## Contents

1. Summary and size
2. Phase −1 status
3. Bucket: branding and lexicon
4. Bucket: content data
5. Bucket: system parameters
6. Bucket: hardcoded mechanics
7. Bucket: AI assets
8. Bucket: schema
9. Bucket: tooling
10. Bucket: documentation (disposition list)
11. Categories the brief did not name (§4F)
12. Licenses
13. Contradictions to discuss
14. Open items

---

## 1. Summary and size

| Bucket | Size | Risk | One-line finding |
|---|---|---|---|
| Branding / lexicon | M | L | ~195 inline `session.send` strings; no banner or MOTD exists at all; brand also lives in infra identifiers (package, env prefix, DB name, storage keys). |
| Content data | M | M | Mostly YAML already, but world content also lives in Python constants and a 278-leaf Python fallback catalog. |
| System parameters | S | L | ~50 per-world numbers, all in a generic shape; they move to world config with no redesign. |
| Hardcoded mechanics | **L** | **H** | Conduit/FRT..PRS in ~12 modules, Digi wallet in 6 plus a column, death billing inside `server.py`, combat calling three subsystems inline, agents welded to Tidegate Isle. |
| AI assets | M | M | Prompts are files but unversioned and name the setting; agent prompts are Python f-strings; LoRAs live inside committed ComfyUI graphs. |
| Schema | M | **H** | Fablestar columns on `characters`/`accounts`; stats blob has no namespacing; Redis has no world prefix and raw keys are built outside `RedisState`. |
| Tooling | **L** | M | Three unsynchronised room writers; duplicated editors; galaxy/system/ship/glyph editors with no content and no runtime. |
| Documentation | S | **H** | 22 tracked `.md` files; the agent-steering ones describe a Fablestar-only engine and contain claims that are false today. |

**Code size.** `src/fablestar` is about 17,600 lines. Largest packages: admin 4,929 · commands
2,673 · agents 1,942 · proficiencies 1,429 · services 1,238 · server.py 757 · world 739. Tests:
`tests/` has 348 passing tests after Phase −1. WorldForge is ~11,000 lines JS/JSX + 349 Rust;
worldforge-mcp 1,750; admin-ui ~10,800; player-ui ~8,300.

**Honest estimate.** The engine core (network, parser, tick, state, content loader, LLM
plumbing) is already close to world-agnostic. The expensive part is not strings; it is that
Fablestar mechanics reach *into* the core (death billing in `server._bootstrap_session`, the
Digi wallet mirrored into a DB column, `resonance_levels_total` in the wire protocol, combat
calling achievements/factions/missions directly) and that both React clients hardcode the
Fablestar character model. Expect Phase 3 to be the bulk of the work, and the two clients to be
a larger share of it than the server.

---

## 2. Phase −1 status

The brief's four bugs were already fixed in code before this work started:

| Brief item | Status | Evidence |
|---|---|---|
| 1. Movement/combat build a fresh `CommandDispatcher` | Fixed | Only instantiation is `sf/server.py:89`; `sf/commands/movement.py:122` and `sf/commands/combat.py:347` call `app_instance.dispatcher`. Guard test added: `tests/test_stabilize_regressions.py`. |
| 2. `destroy_session` leaves ghost players | Fixed (in the session loop, not in `destroy_session`) | `sf/server.py:686-696` removes the player from the room set; `SessionManager.owns_player` (`sf/network/session.py:128-132`) treats a missing mapping as owned, so the admin disconnect path (`sf/admin/routes/admin_ops.py:281`) is covered too. Guard tests added for both paths, mutation-checked. |
| 3. `say` wrong import path | Fixed | `sf/commands/communication.py:3-7,63`; covered by `tests/test_input_and_comms.py:65`. |
| 4. Client parses only first WS frame | Fixed | `player-ui/src/App.jsx:2198-2202` parses every frame. player-ui has no test runner, so there is no automated guard. |

The audit found three real breakages, fixed on this branch before any refactor:

| Commit | What now refuses that didn't before |
|---|---|
| `2a80ab9` | An admin-ui World Builder positions save (or room delete) no longer erases the `floors` map WorldForge and worldforge-mcp write (`sf/admin/content_browser.py:26,420-426` rebuilt the doc without it). Verified with a real PUT through Nexus: 31 floor entries before and after. |
| `3d4cf48` | A tick handler that raises is logged with its name and traceback (deduped per 240 ticks) instead of being discarded by `gather(return_exceptions=True)` (`sf/core/tick.py:38-40`). |
| `6e27147` | Hot-reloading a command module removes commands and aliases deleted from its source; a failed reload restores the previous set (`sf/commands/registry.py:32-38` only ever overwrote). |

Flagged, not fixed (owner calls):

- `docker-compose.yml:17-20` commits a literal fallback Postgres password (`SECURITY.md:42` mentions it).
- Field proficiency gains never fire because of the depth gate (`sf/proficiencies/engine.py`, owner decision pending in `docs/design/AGENT_LIFE_ROADMAP.md` item 9).
- Server log on a normal boot shows `Room file not found` for `starter_zone:station_street` (zone deleted 2026-09-12, still referenced from live state) and `aipub:apartment_3/4` (owner WIP deletes in the working tree).

---

## 3. Bucket: branding and lexicon

**Size M · Risk L.** Mechanical once a lexicon service exists, but touches many files.

### Player-facing strings in the server

- **No login banner, MOTD or welcome text exists** anywhere in the server. The play connection
  is a JSON handshake; errors are machine codes (`sf/server.py:379-438`). Brief decision 7 asks
  for these to be world-supplied, so they are new features, not extractions.
- **Prompt line** hardcoded: `"\r\n> "` at `sf/network/session.py:44`.
- **Help** is built from handler docstrings (`sf/commands/info.py:144-167`), ~41 commands.
- **Inline sends:** ~170 `session.send(...)` in `sf/commands/` (items 32, communication 18,
  info 17, shop 17, combat 15, crafting 13, missions 10, proficiency 10, search 10, effects 8,
  movement 7, rent 6, achievements 4, factions 3) plus ~25 in `server.py`,
  `parser/dispatcher.py:88,108,112`, `effects/manager.py`, `maestro/modules.py`,
  `factions/engine.py:43,77`, `factions/missions.py`, `achievements/engine.py:104-105`.
- **Clearly world-specific strings** (~35 sites): "Digi" (`commands/shop.py` ×7,
  `commands/rent.py:142,167`, `factions/missions.py:131`), "— Conduit —" / "Resonance"
  (`commands/proficiency.py:49-51,126,161,176`), "The station is silent."
  (`commands/communication.py:167`), "the clinic, say… diagnostic bed… station's hum"
  (`commands/effects.py:40,65`), "AIpub bar" / "Tidewater Bunkhouse" (`commands/rent.py:83,93`),
  clinic wake text (`server.py:508-516`), "You succumb to your afflictions"
  (`effects/manager.py:67`), maestro "dread" station lines (`maestro/modules.py:95-102`).
- **In-fiction LLM fallback strings** in engine code: `sf/llm/client.py:367-371`
  ("Connection to the Forge lost", "The engine hums…"), `sf/llm/validation.py:36`.
- **Command aliases as vocabulary:** `wallet` aliases `digi`, `money` (`commands/shop.py:357`);
  `prof` aliases `conduit`, `resonance` (`commands/proficiency.py:34,98`).

### Player UI (`player-ui/src`)

- Title "Fablestar Expanse — Player" (`index.html:7`); `<h1>FABLESTAR</h1>` (`App.jsx:246`);
  "Expanse — enter your conduit" (`App.jsx:280`); "Enter the Expanse" (`App.jsx:1895`);
  header "FABLESTAR" (`mud/FablestarClient.jsx:309`); "— Connected to Fablestar Expanse —"
  (`mud/03-narrative.jsx:71`); "Connection to the station lost" (`FablestarClient.jsx:275`);
  "You left the station." (`App.jsx:2305-2307`); download name `fablestar-scene-*`
  (`App.jsx:2467`).
- Currency label fallbacks "pixels" / "Digi" in ~15 places even though the server sends both
  names (`App.jsx:34,54,663,900,988,2002-2128`; `FablestarClient.jsx:77,359,372,452`).

### Admin UI (`admin-ui/src`)

- "Fablestar Admin" (`App.jsx:78`), nav logo "FABLESTAR" (`App.jsx:398`), header comment
  (`App.jsx:12`), `AiForgePage.jsx:639`.
- Digi labels in `AgentsTab.jsx` (216,231,394,408,433) and `ShopsTab.jsx` (53-131).

### Infrastructure identifiers (engine branding, distinct from world branding)

These are "Fablestar" as the *engine's* name. They rename to SAGE; they do not move to a world.

| Identifier | Location |
|---|---|
| Python dist/package `fablestar`, console script | `pyproject.toml:2`; `src/fablestar/` |
| `FablestarServer` class (~20 type-hint sites) | `sf/server.py:69` |
| Hot-reload module path parsing looks for the `"fablestar"` path segment | `sf/server.py:709-714` |
| FastAPI title "Fablestar Nexus API" | `sf/admin/nexus.py:74` |
| Env prefix `FABLESTAR_` (+ `FABLESTAR_ADMIN_JWT_SECRET`, `FABLESTAR_PROJECT_ROOT`) | `sf/core/config.py:143-164`; `sf/core/security.py:16,24` |
| DB name/user `fablestar` | `sf/core/config.py:45-46`; `docker-compose.yml` |
| Auto-written TOML headers "Fablestar Nexus" | `sf/core/llm_persist.py:15`, `comfyui_persist.py:15`, `agents_llm_persist.py:15` |
| localStorage keys `fablestar_*` | `admin-ui/src/adminCommon.jsx:8`, `AdminThemeContext.jsx:4`; `player-ui/src/PlayThemeContext.jsx:4`, `mud/03-narrative.jsx:11-14` |
| Tauri `productName` "Fablestar WorldForger", identifier `com.fablestar.worldforge` | `worldforge/src-tauri/tauri.conf.json:3,5,17` |
| worldforge-mcp instructions "for Fablestar MUD" | `worldforge-mcp/server.py:29` |
| ComfyUI node titles `Fablestar_Scenegen_*` | `config/comfyui_scene_workflow.json` |
| Log lines "Fablestar MUD Platform starting up" | `sf/server.py:298,344` |

---

## 4. Bucket: content data

**Size M · Risk M.** YAML moves cleanly; Python-embedded content needs extraction.

### On disk (`content/`)

| Dir | Files | Loader |
|---|---|---|
| `content/world/zones/` | `test_isle` "Tidegate Isle" (zone.yaml, `.positions.json`, 31 rooms), `aipub` (zone.yaml, `.positions.json`, 9 rooms) | `sf/world/loader.py:53-56`; map at `sf/server.py:614-648` |
| `content/world/entities/` | 5 | `sf/world/loader.py:77,115` |
| `content/world/items/` | 16 | `sf/world/loader.py:94,108,127` |
| `content/world/galaxy.yaml` | 3 lines, `systems: []` | admin only (`sf/admin/content_browser.py:24,678-710`); no runtime loader |
| `content/achievements/` | 17 | `sf/achievements/registry.py:36-38` |
| `content/agents/` | 8 personas | `sf/agents/registry.py:31-32` |
| `content/factions/` | 2 | `sf/factions/registry.py:36-37` |
| `content/proficiencies/` | `catalog.json` (278 leaves), `leaf_descriptions.json`, `manifest.yaml`, `mouseover/*.pipe.txt` ×11 (build input) | `sf/proficiencies/catalog_loader.py:79-126` |
| `content/world_backup_20260426_090536/` | 55 files, 28 MB, **untracked** — old sci-fi zones (nova_kepler, starter_zone, stellar_grounds_cafe), `systems/` ×5, `ships/corvette.yaml`, `stamps/`, `items/resonance_shard.yaml` | none |

Things in `content/` that are tooling or build data rather than world data:
`proficiencies/manifest.yaml` (validation), `zones/*/.positions.json` (editor layout, also
read by the runtime map), `mouseover/*.pipe.txt` (build input only).

Directories code references but that do not exist under `content/world/`: `glyphs/`
(`sf/admin/content_browser.py:21,251`, admin nav), `systems/` and `ships/`
(`content_browser.py:22-23,697-1066`), `stamps/` (WorldForge only).

### World content embedded in Python

| What | Location |
|---|---|
| Start and respawn rooms `test_isle:ferry_landing`, `test_isle:clinic` | `sf/world/defaults.py:3-4`; ORM default `sf/state/models.py:95` |
| 278 proficiency leaves across 11 Fablestar domains (fallback when catalog.json missing) | `sf/proficiencies/data/*.py`, `EXPECTED_LEAF_COUNT` at `data/__init__.py:18` |
| Maestro event modules (ambush/mercy/dread), `ration_pack`, station lines | `sf/maestro/modules.py:34-117` |
| Crafting and search leaf ids | `sf/commands/crafting.py:16-21`; `sf/commands/search.py:12` |
| Combat proficiency leaf pool | `sf/commands/combat.py:153-158`; `sf/proficiencies/state_helpers.py:90-95` |
| Hazard resist leaf | `sf/effects/hazards.py:10` |
| Equipment slots `("weapon","armor")` | `sf/items/equipment.py:14` |
| Faction standing ladder | `sf/factions/models.py:6-17` |
| Day phases, "island day" | `sf/world/clock.py:3,9-10` |
| Agent world knowledge (shops, creatures, items, AIpub) | `sf/agents/brain.py:122-130,369`; `sf/agents/manager.py:514,685-690,769-772` |
| Achievement tier names | `sf/achievements/models.py:6-16` |
| Room type list (12 values) | `worldforge/src/panels/RoomPanel.jsx:9`; `admin-ui/src/builder/RoomPropertyPanel.jsx:31-44`; `worldforge-mcp/server.py:350-363` |

---

## 5. Bucket: system parameters

**Size S · Risk L.** Generic shape, per-world value. These become world config keys.

| Parameter | Value | Location |
|---|---|---|
| tick_rate | 0.25 s | `sf/core/config.py:16` |
| starting in-world currency / name | 100 / "Digi" | `sf/core/config.py:22,24` |
| AI-art starting credits / portrait / area / chargen cost | 50 / 3 / 3 / 3 | `sf/core/config.py:77-80` |
| AI-art currency name / pixels_per_usd | "pixels" / 100 | `sf/core/config.py:81-83` |
| persistence flush | 240 ticks | `sf/state/persistence.py:24` |
| spawn check / litter sweep / litter TTL | 20 / 480 ticks / 30 min | `sf/world/spawner.py:16-19` |
| loot default chance | 0.6 | `sf/world/models.py:111` |
| ambient check; line interval | 8 ticks; 45–120 s | `sf/world/ambient.py:23`; `sf/world/models.py:47-48` |
| day length / phases | 40 min / 4 | `sf/world/clock.py:9-10` |
| search max_finds / respawn / chance; level bonus / cap | 1 / 600 s / 0.7; 0.005 / 0.95 | `sf/world/models.py:16-18`; `sf/commands/search.py:14-15` |
| shop buy / resale / stock cap; ledger cap | 0.5 / 1.0 / 20; 200 | `sf/world/models.py:63-68`; `sf/commands/shop.py:54` |
| lodging price / lease / renew window | 15 / 80 min / 15 min | `sf/world/models.py:78-79`; `sf/commands/rent.py:22` |
| respawn bill (players / agents); respawn hp; default max_hp | 10 / 10; max_hp//2; 100 | `sf/server.py:462,476,480`; `sf/agents/manager.py:34` |
| entity defaults hp / atk / def | 10 / 3 / 1 | `sf/world/models.py:122-123` |
| damage roll; flee chance | atk + d6 − def, min 1; 0.5 | `sf/commands/combat.py:30-34,342` |
| effects interval; hazard tick / duration / resist cap | 8 ticks; 6 s / 6×(2+sev) / 0.75 | `sf/effects/manager.py:20`; `sf/effects/hazards.py:12,50-51` |
| rest HoT | +2 / 5 s / 30 s | `sf/commands/effects.py:58-60` |
| maestro interval / cooldown / nothing-weight | 120 / 90–240 s / 60 | `sf/maestro/director.py:22-24` |
| faction rep range; defaults kill/enemy/mission/pay; mission counts | ±200; −10/+2/+10/12; kill 3–5, collect 2–3 | `sf/factions/models.py:16-17,36-46`; `sf/factions/missions.py:24-25` |
| proficiency caps total / leaf; gain chance; branch gate; decay floor | 5000 / 200; 0.35–0.65 (VR ×0.75); tier×5; 0.75×peak | `sf/proficiencies/engine.py:27-28,68,168-171`; `state_helpers.py:110-111` |
| chargen stat points / range / default; starter budget / per-leaf | 65 / 8–23 / 13; 15 / 5 | `sf/proficiencies/bonus.py:10-12,75`; `starter.py:11-12` |
| agent tick / lease sweep / inventory cap; flee / eat hp fraction | 8 / 240 / 12; 0.30 / 0.60 | `sf/agents/manager.py:33-36`; `sf/agents/body.py:22-24` |
| command rate limit; max input | 8/s burst 20; 1000 chars | `sf/parser/dispatcher.py:14-18` |
| max characters per account; play token TTL | 8; 7 days | `sf/services/player_service.py:83`; `sf/services/play_tokens.py:19` |

---

## 6. Bucket: hardcoded mechanics

**Size L · Risk H.** This is the core of the work.

| Subsystem | LOC | Fan-in | Verdict | Fablestar coupling |
|---|---|---|---|---|
| `proficiencies/` (Conduit) | 1,429 | 15 src | Tree/registry generic in shape; stat model and data are Fablestar | `StatKey = Literal["FRT","RFX","ACU","RSV","PRS"]` (`models.py:7,38`), `ConduitAttributes` (`models.py:74-91`), `CONDUIT_KEY="conduit"` (`state_helpers.py:15`), legacy STR/DEX mapping (`state_helpers.py:35-51`), combat formula with 4 leaf ids (`state_helpers.py:75-107`), chargen 65 points (`bonus.py:10-12,49,63`), `"resonance_cap"` (`engine.py:189`), placeholder tick never registered (`tick.py:4`) |
| Death / respawn | — | core | **Fablestar mechanic inside `server.py`** | `_bootstrap_session`: hp ≤ 0 → `RESPAWN_ROOM`, bill `min(digi,10)`, "dying has a price on Tidegate" (`sf/server.py:462-516`); wallet mirror `norm_stats["digi"]` (`:500`) |
| Wallet (Digi) | — | 6 modules | Generic shape, hardwired name and storage | `stats["digi"]` in `commands/shop.py:39-40`, `commands/rent.py:107,147`, `factions/missions.py:129`, `agents/manager.py:111-122,331`; `digi_pending:{name}` Redis key; mirrored to `characters.digi_balance` (`sf/state/persistence.py:62-63`) |
| `commands/combat.py` | 349 | 2 | Generic flow, Fablestar resolver, inline cross-calls | `combat_attack_defense_from_stats` (`:85`), leaf pool (`:153-158`), **inline calls to achievements, factions and missions** (`:177-228`) |
| `commands/proficiency.py` | 226 | 1 | Fablestar | Conduit/Resonance display (`:49-51,126,161,176`) |
| `commands/shop.py` | 366 | 2 | Generic shop, Digi-bound | as above |
| `commands/rent.py` | 169 | 2 | Generic lodging, flavored strings | lease sweep **run from the agents manager** (`sf/agents/manager.py:289-295`) |
| `commands/crafting.py`, `search.py`, `movement.py` | 245 / 124 / 153 | 1 each | Generic flows with world leaf ids and gain curves | `movement.py:89` reads `conduit` directly |
| `commands/effects.py` | 65 | 1 | Flavored | rest requires `room.type == "safe"` (`:39`) |
| `effects/` | 316 | 4 | Engine generic; hazards Fablestar-flavored | hazard resist reads `stats[CONDUIT_KEY]` (`hazards.py:10,17`) |
| `achievements/` | 214 | 12 | Generic | counter names defined at call sites across commands |
| `factions/` | 316 | 3 | Mostly generic | payout hardwired to `stats["digi"]` and "Digi" string (`missions.py:129-131`) |
| `items/equipment.py` | 87 | 3 | Generic, fixed slots | `SLOTS` (`:14`); `ItemTemplate` fixed attack/defense/heal/ammo/recipe fields (`sf/world/models.py:143-166`) |
| `maestro/` | 225 | 1 | Director generic; modules are Python content | see §4 |
| `agents/` | 1,942 | 1 (+4 test files) | **Heavily Fablestar** — owner ruling: whole system becomes a plugin | clinic bill, AIpub social room, `aipub:main_bar`, ration items, Digi thresholds, "space-station MUD" prompts (`manager.py:34,346-371,514,640-772`; `brain.py:89,118,122-130,369`); persona `attributes` FRT..PRS and `digi` (`models.py:37-41`); also agents are excluded from admin player lists in several routes |
| `world/models.py` glyph/ship/system | — | admin only | **Dead** | `StarSystemModel`, `ShipTemplate`, `GlyphModel` (`:189,210,230`) have no runtime use and no content |
| `RoomModel` | — | core | Engine model carries plugin fields | `shop`, `lodging`, `hazards`, `ambient`, `features.search` (`sf/world/models.py:82-97`) |
| Play protocol | 103 | core | Engine protocol carries Fablestar vocabulary | `resonance_levels_total`, `digi_balance`, `echo_credits`, `reputation` in `sf/network/play_messages.py:40-103`; snapshot built at `sf/server.py:527-590` |

### Client-side mechanics (player-ui)

| Panel | Location | Coupling |
|---|---|---|
| Character "Conduit" | `mud/06-panels-b.jsx:112-369` | reads `stats.conduit.conduit_attributes` (`:132`); FRT..PRS (`:344-348`); "Mana" placeholder; "Resonance" vs `RESONANCE_CAP=5000` (`:8,313`); "Madness = 100−RSV" (`:147-148`) |
| Glyph Loadout | `mud/06-panels-b.jsx:371-401` | **mock data only** |
| Quest Journal, Target, Session Stats, Keybinds | `mud/04-panels-a.jsx:57-199` | **mock data only**, Fablestar names |
| Skills | `mud/07-proficiencies-panel.jsx` (612 lines) | caps 5000/200 (`:6-7`); catalog from `/play/proficiencies/catalog` |
| Chargen | `ChargenProficienciesStep.jsx:58,121`; `App.jsx:972,980` | "Conduit preview", hardcoded budget "(15)" and max 5 in error text |
| Reputation | `ReputationThermometer.jsx` | fixed −100..+100 Evil/Good |
| Command autocomplete | `mud/03-narrative.jsx:1363` | 50-command literal list that "mirrors the server registry" |

### Admin-ui mechanics

`ProficienciesPage.jsx:6,14` (`WEIGHT_KEYS` FRT..PRS), `AgentsTab.jsx` (Digi, feelings, brain
settings), `ShopsTab.jsx` (Digi), `PlayerAccountsTab.jsx:6-12` (hardcoded USD pixel bundles),
`:372,481,507`, `AiForgePage.jsx:22-104` (lore zone names that do not exist in content, glyph
tiers, "Fellow Conduit"), `PlayersPage.jsx:85` ("Glyphs" column), `DashboardPage.jsx:152`.

---

## 7. Bucket: AI assets

**Size M · Risk M.** Brief decision 6: engine keeps routing/caching/retries/queue/cost; world
owns prompts, tone, style tokens, LoRAs, NPC priors, content rules.

### Prompt templates (`prompts/`, 7 files, 135 lines, no version field anywhere)

| Template | Used by | World coupling |
|---|---|---|
| `room_description.j2` | `sf/commands/info.py:51` | "Fablestar MUD, a dark, ancient sci-fi world…" (`:2`), tone (`:7`) |
| `combat_narration.j2` | `sf/commands/combat.py:266` | "Fablestar MUD…" (`:2`), tone (`:8`) |
| `forge_room.j2` | `sf/admin/routes/forge.py:64` | "architect of the Fablestar MUD" (`:2`), style (`:31`); schema block is engine-shaped |
| `forge_generic.j2` | `forge.py:117` | "FABLESTAR CONTENT FORGE", "labyrinth, glyphs, resonance" (`:2-3`), glyph schema (`:23`) |
| `forge_area_image_prompt.j2`, `forge_portrait_character_prompt.j2`, `play_scene_image_prompt.j2` | `sf/services/scene_service.py:157,197,240` | "dark sci-fi MUD", "Sci-fi, atmospheric" |

Loader: `sf/llm/prompts.py:17` hardcodes the cwd-relative `"prompts"` dir.

### Prompts and style in Python (not files)

- Agent brain f-strings: `sf/agents/brain.py:77-135,330,368-378,440-441`.
- Default system prompts "master storyteller for a dark sci-fi MUD": `sf/llm/client.py:296,355`,
  `sf/agents/embedded_llm.py:105`.
- Image-prompt system prompts: `sf/services/scene_service.py:167,205-208,248-251`; forge
  `sf/admin/routes/forge.py:127`; agent brain test "weary space-station dockworker"
  `sf/admin/routes/agents.py:131-135`; portrait default "science fiction RPG character"
  `sf/services/player_service.py:88-93`.
- Output validation regex forbidding hp/mana/level/XP talk: `sf/llm/validation.py:16-21` —
  this is a *content rule*, which the brief assigns to the world. Combat narration skips it
  (`sf/commands/combat.py:266-272`).

### Image generation

| File | Style carried |
|---|---|
| `config/comfyui_character_portrait_workflow.json` (default portrait) | LoRA `Butternutcrunch_PolyPop` (`:124`), empty negative, background removal node |
| `config/comfyui_scene_workflow.json` (default area) | same LoRA (`:195`), node titles `Fablestar_Scenegen_*` |
| `config/comfyui_area_workflow.json` (legacy) | LoRA `Promtwaffle_Rusted_Horizons` (`:665`), SeedVR2 upscaler |
| `config/*.example.json` ×3 | sci-fi example prompts, generic negatives |

`sf/comfyui_client.py` itself is generic (injects the prompt verbatim, no style tokens).
Style therefore lives in two places: prompt templates and LoRAs inside workflow graphs.

### Engine-side AI plumbing (stays in engine)

| Concern | Where | Gap vs brief decision 6 |
|---|---|---|
| Provider routing (LM Studio / Ollama / embedded) | `sf/llm/client.py:105-150,306-312` | — |
| Circuit breaker 30 s; status probe cache 60 s | `sf/llm/client.py:19,88,271-346`; `sf/agents/embedded_llm.py:109-126` | — |
| Response cache | none; `LLMConfig.cache_ttl` persisted and editable but unused (`sf/core/config.py:86-102`) | caching missing |
| Retries | none | missing |
| Queueing | narration drop-not-queue per player (`info.py:69-76`, `combat.py:258-279`); agent budgets (`brain.py:25-30,236`); nothing server-side for ComfyUI | partial |
| Cost control | AI-art credit ledger: debit before, refund on failure, row lock (`sf/services/economy.py:42-88`) | present |
| Unused config | `LLMConfig.anthropic_key` declared, never read | — |

NPC behaviour priors: `content/agents/*.yaml` (8 personas) plus the hardcoded knowledge in
`brain.py` and `manager.py` (§4).

---

## 8. Bucket: schema

**Size M · Risk H.** Data migrations are the one-way doors in this project.

### Postgres (`sf/state/models.py`, 11 alembic revisions)

| Table.column | Fablestar assumption |
|---|---|
| `characters.digi_balance` int (`models.py:97`, rev `d5e6f7a8b9c0`) | named in-world currency as a column |
| `characters.reputation` int (`models.py:101`, rev `f6e7…`) | good/evil moral axis |
| `characters.room_id` ORM default `test_isle:ferry_landing` (`models.py:95`) | world start room |
| `characters.stats` **JSON** (not JSONB) (`models.py:105`) | default blob embeds legacy STR/DEX/INT/PER *and* `conduit.conduit_attributes{FRT..PRS}` (`models.py:13-32`) |
| `characters.portrait_url/portrait_prompt/last_scene_image_url` | AI layer — engine, generic |
| `accounts.echo_credits` int (`models.py:47`, rev `b3c4d5e6f7a8`) | AI-art credit; engine cost control, Fablestar-named |
| `agent_state` table (rev `k4l5…`) | agents — plugin per owner ruling |
| `account_scene_images`, `admin_staff`, `accounts` rest | generic |

Stats blob top-level keys, each owned by convention with no namespace or schema:
`conduit` (proficiencies) · `counters`, `achievements`, `visited_rooms` (achievements) ·
`effects` · `factions`, `mission` · `equipment` · `digi` (shop/rent/missions) · `home_room`,
`home_until` (rent) · `hp`, `max_hp` · `feelings`, `agent_memories`, `is_agent`,
`progress_log` (agents). TypedDict contract: `sf/state/state_types.py:18-48` (docstrings at
`:41,52,62` describe key patterns that don't match the real ones).

### Redis

- `RedisState.KEY_PREFIXES` (`sf/state/redis_client.py:24-36`) via `_get_key` (`:83-84`):
  `player:{id}:location|session|stats|inventory`, `room:{id}:players|entities|items`,
  `combat:{id}`, `entity:{id}:state`, `item:{id}:state`, `search:{room}:{feature}:finds`.
  **No namespace.** `RedisConfig` has host/port/db/password only (`sf/core/config.py:51-55`).
- Raw keys built outside `RedisState`: `rentals` (`commands/rent.py:21`), `shopstock:{room}`,
  `shopledger:{room}` (`commands/shop.py:39,65`; `admin/routes/shops.py:51`),
  `digi_pending:{name}` (`shop.py:91`; `agents/manager.py:331`), `heat:{map}`
  (`sf/telemetry.py:76,85`); pattern scans `room:*:players` (`admin/world_live.py:37`) and
  `room:*:items` (`world/spawner.py:62`).
- `get_all_active_player_ids` splits keys on ":" and takes index 1 (`redis_client.py:78-79`)
  — breaks the moment a prefix is added.
- Player ids are character names, shared with agents.

---

## 9. Bucket: tooling

**Size L · Risk M.**

| Tool | Stack / size | Reads/writes | Fablestar assumptions |
|---|---|---|---|
| **WorldForge** (`worldforge/`) — owner ruling: this is "the map tool" | Tauri 2 + React 19, @xyflow, elkjs; ~11,000 JS + 349 Rust; 36 vitest cases; fully built | Direct disk via Tauri `write_file` (atomic, `..` rejected, `src-tauri/src/commands.rs:26-60,84-87`): rooms, entities, items, glyphs, systems, galaxy, ships, `.positions.json` v2 (with floors), `groups.yaml`, stamps | Branding (`App.jsx:33-54`, `tauri.conf.json`); tree `content/world/{zones,stamps,entities,items,systems,ships,glyphs}` (`utils/worldScaffold.js:1-105`); scaffold writes `starter_zone` (deleted zone); 12 room types (`panels/RoomPanel.jsx:9`); glyph/ship/galaxy schemas; does **not** cover `RoomModel.shop/lodging/ambient/features.search`. Calls Nexus for `/forge/*` generation and scene art. |
| **worldforge-mcp** (`worldforge-mcp/server.py`) | FastMCP, 1,750 lines, 15 tools, no tests | Direct disk: room YAML, `zone.yaml`, `.positions.json` v2 | "for Fablestar MUD" and space-station examples in the ~285-line instructions (`:28-313`); 12 room types (`:350-363`); `validate_zone` reads `glyphs/`, applies Epitaph density metric (`:1534-1739`); non-atomic `create_zone`/`delete_room` writes (`:720-721,922-925`) |
| **admin-ui World Builder** (`admin-ui/src/builder/`) | React + @xyflow, ~4,500 lines | Via Nexus `/content/*` (`sf/admin/routes/content.py`, `sf/admin/content_browser.py`) with `expected_mtime` 409 guard | `galaxy_id: "fablestar"` literal (`content_browser.py:710`); GalaxyView/SystemView/ShipEditor over dirs that don't exist; 12 room types, only 6 exit directions (`RoomPropertyPanel.jsx:31-46`); **no floor support** (the data loss fixed in `2a80ab9`) |
| **Nexus admin console** (`admin-ui/`, rest) | React, ~6,300 lines outside builder | Nexus REST | see §3, §6 |
| `scripts/` | 4 maintenance scripts | DB, proficiency catalog | proficiency catalog build is Fablestar data |
| Sibling repos in `F:\Cursor Projects\` | WorldWeaver (Svelte/Tauri terrain brush), terrain-forge (Rust wgpu), Feyndral City Map Maker (Electron) | none reference Fablestar content | unrelated; out of scope |

### Overlap

| Capability | WorldForge | worldforge-mcp | admin-ui Builder |
|---|---|---|---|
| Room CRUD | disk | disk | HTTP + mtime guard |
| Exits | 10 directions | 10, same-zone only | 6 |
| Graph canvas | xyflow | — | xyflow |
| Auto-layout | ELK (`utils/autoLayout.js`) | BFS offsets | ELK — **byte-identical copy** (`builder/AutoLayout.js`) |
| Floors | yes | yes | no |
| Stamps / groups / notes | yes | — | — |
| Validation | `utils/validation.js` | `validate_zone` (port of the app's checks) | `builder/ValidationPanel.jsx` (separate, smaller) |
| Galaxy / system / ship | yes | — | yes |
| Entity / item / glyph editors | yes | read-only | Content Library |
| shop / lodging / ambient / search | — | — | — |

Three unsynchronised writers to the same files (`CLAUDE.md` "How WorldForge saves";
`docs/architecture.md:257-265`).

---

## 10. Bucket: documentation — disposition list

**Size S · Risk H.** 22 tracked `.md` files (`git ls-files '*.md'`). No `.cursorrules`,
`.cursor/rules`, `AGENTS.md` or `.mdc`. `.claude/` is gitignored (local only). Non-`.md`
steering text: `worldforge-mcp/server.py:28-313` instructions and `prompts/*.j2`, covered in
§7 and §9.

Classes: **A** agent-steering · **E** engine doc · **W** world doc · **H** historical ·
**C** contradictory. "Now" = done on this branch before Phase 2; "Later" = in the phase that
touches the matching code.

| # | File | Class | Misleads a future session? | Action |
|---|---|---|---|---|
| 1 | `CLAUDE.md` | A, E, C | **Yes.** Describes "Fablestar is a text MUD engine", Conduit/FRT..PRS as core; claims content is gitignored (it is tracked), lists `ships/ systems/ stamps/` dirs that don't exist, says EventBus publishes tick (unused), room type enum of 4 (tools use 12), "known issue" nested content (fixed), "don't mock the database" (suite is hermetic with `tests/fakes.py`), package list missing 7 packages | **Now:** SAGE banner + correct the false claims. **Later:** rewrite engine sections as each phase lands. |
| 2 | `REXYMCP.md` | A | Mildly — "Fablestar MUD Platform project"; gates target `src tests` only | **Now:** banner. **Phase 2:** update gate paths when `engine/` exists (also `rexymcp.toml`). |
| 3 | `README.md` | E, W, C | **Yes.** "A sci-fi MUD engine" (`:5`); WorldForge "write-through saving via the forge API" (`:40`, false); references missing screenshots | **Now:** banner + fix the WorldForge claim. **Later:** split into engine README and world README. |
| 4 | `SECURITY.md` | E | No | **Later:** rename branding; owner call on the compose password it references. |
| 5 | `admin-ui/README.md` | E | Low | **Later** (Phase 3/5). |
| 6 | `player-ui/README.md` | E, W | Low — describes Conduit picker as the client's chargen | **Later** (Phase 3). |
| 7 | `player-ui/src/CONVENTIONS.md` | A (frontend) | No | Keep. |
| 8 | `worldforge/README.md` | E, W | Medium — "map editor for Fablestar zones" | **Later** (Phase 5). |
| 9 | `docs/architecture.md` | E, C | **Yes.** "Fablestar — Architecture"; "M1 in progress" (M1 is done); "no event bus" vs CLAUDE.md; "no in-process LLM inference" (embedded llama exists); Conduit as a core engine component (`:85-87,209-213`); ORM list omits `agent_state` | **Now:** banner + fix the status line. **Later:** becomes the SAGE engine architecture doc in Phase 2. |
| 10 | `docs/design/AGENT_LIFE_ROADMAP.md` | W | No (world design) | **Later:** relocate to `worlds/fablestar/docs/`, and note agents are now a plugin. |
| 11 | `docs/design/EPITAPH_LESSONS.md` | E/W mix, C | **Yes.** Proposes putting ambient/search/effects/factions into core `RoomModel`/engine (`:107-156`), "for our starship setting" | **Flag for conversation** (§13). No rewrite until discussed. |
| 12 | `docs/dev/NEXT.md` | A | Yes — says no active phase | **Now:** point at SAGE, awaiting Phase 1 review. |
| 13 | `docs/dev/STATUS.md` | A, E, W | Medium — "Glyph runtime — glyph content exists" (`:302`) but content only exists in the untracked backup; "34 vitest" (36 now) | **Now:** banner. |
| 14 | `docs/dev/STANDARDS.md` | A (generic) | Low — mentions CI that does not exist (`:170,197`) | **Phase 2a** when CI lands. |
| 15 | `docs/dev/WORKFLOW.md` | A (generic) | No | Keep. |
| 16 | `docs/dev/WORLDFORGE_AUDIT.md` | H, C | Medium — criticals 7/8 shown open, fixed since; "no validate_zone" now wrong | **Now:** historical header. |
| 17 | `docs/dev/QA_PLAYTEST_2026-09-13.md` | H | No | **Now:** historical header. |
| 18 | `docs/dev/QA_FIX_PLAN_2026-09-13.md` | H | No | **Now:** historical header. |
| 19 | `docs/dev/SOAK_2026-09-13.md` | H | No | **Now:** historical header. |
| 20 | `docs/dev/milestones/M1-code-quality-foundation/README.md` | H, C | Low — "completed" with phases 02/03 "todo" and files missing; "green CI baseline" with no CI | **Now:** historical header. |
| 21 | `docs/dev/milestones/M1-code-quality-foundation/phase-01-parser-registry-tests.md` | H | No | **Now:** historical header. |
| 22 | `docs/screenshots/README.md` | E | No | **Later** (Phase 5). |
| 23 | `docs/dev/milestones/M2-sage-decoupling/README.md` | A | No — created by this work | Keep current as stages land. |

Rows 1–22 are the files that existed before this work; row 23 was added by it. `docs/sage/*.md` files are authoritative per the brief's precedence
order and are not counted above.

---

## 11. Categories the brief did not name (§4F)

1. **Wire protocol vocabulary.** The engine↔client contract (`sf/network/play_messages.py`,
   snapshot at `sf/server.py:527-590`) carries `resonance_levels_total`, `digi_balance`,
   `echo_credits`, `reputation`, and passes the raw stats blob so clients dig into
   `stats.conduit.*`. The protocol is its own decoupling surface, separate from strings.
2. **Client-duplicated mechanics.** Both React clients re-encode Fablestar rules: caps 5000/200,
   chargen budget, stat keys, a 50-command autocomplete list, and four mock panels for
   mechanics that don't exist (Glyph Loadout, Quest Journal, Target, Session Stats).
3. **Two different kinds of currency.** In-world Digi (world mechanic) vs the account-level
   AI-art credit "pixels" (`accounts.echo_credits`), which is operator cost control and
   therefore **engine** under brief decision 6 — only its display name is world lexicon.
   Admin also hardcodes USD bundle prices (`admin-ui/src/PlayerAccountsTab.jsx:6-12`), which
   is deployment/commercial config, neither engine nor world.
4. **Cwd-relative literal paths.** ~15 sites hardcode `content/…`, `prompts`, `config/…`
   outside the `resolve_project_root` helper (`sf/world/loader.py:30,55`, `sf/server.py:332,619`,
   `sf/admin/content_browser.py:18-24,1087`, `sf/admin/routes/shops.py:18`,
   `routes/agents.py:23`, `routes/play.py:108-109`, `sf/llm/prompts.py:17`, the three
   registries, the three `*_persist.py`). A world package needs one path resolver.
5. **Tests coupled to live Fablestar content.** `tests/test_achievements.py:111`,
   `test_agents_body.py:95`, `test_factions.py:84`, `test_search.py:61,71`,
   `test_proficiencies.py:37-64`, `tests/fakes.py:125` read `content/`. They need world
   fixtures before content moves.
6. **No CI at all.** Invariant enforcement (brief §3) needs CI to exist first; STANDARDS.md
   and the M1 README already claim it does. `rexymcp.toml` gates cover only `src tests`.
7. **Dead world code.** `StarSystemModel`, `ShipTemplate`, `GlyphModel`, galaxy/system/ship/
   glyph editors in two apps, glyph admin tab, mock client panels — Fablestar assumptions with
   no runtime and no content. Under brief §8 "prefer deleting", these are delete candidates,
   not extraction candidates.
8. **Engine models carrying plugin fields.** `RoomModel.shop/lodging/hazards/ambient/
   features.search` and `ItemTemplate.attack/defense/heal/ammo/recipe`. Room and item YAML
   schemas need an extension mechanism, not just stats.
9. **Protocol and admin exclusions for agents.** Agents are filtered out of player lists and
   counts in admin routes; with agents as a plugin, the engine needs a generic "session kind"
   rather than `is_agent` checks.
10. **Shared global Python interpreter.** No venv; the interpreter has GPL/LGPL packages outside
    the lock and versions that differ from `requirements.lock`. A trustworthy license audit
    and reproducible CI both need a clean environment.

---

## 12. Licenses

Brief decision 4 asks for an early license audit ahead of a possible paid release.

| Finding | Where | Note |
|---|---|---|
| ~~**No LICENSE file**; `pyproject.toml` declares MIT~~ | repo root | **Resolved 2026-09-13:** engine licensed `FSL-1.1-ALv2` (`engine/LICENSE`), Fablestar content proprietary (`NOTICE`). |
| `elkjs@0.11.1` **EPL-2.0** — direct dependency | `admin-ui`, `worldforge` | Weak copyleft; fine to use unmodified and bundled, but modifications must be released. Flag for any commercial distribution of WorldForge. |
| MPL-2.0 transitives | `lightningcss` (admin-ui, player-ui build toolchain); `cssparser`, `selectors`, `dtoa-short`, `option-ext` (WorldForge Rust); `certifi` (Python) | File-level copyleft; normally fine unmodified. |
| CC-BY-4.0 | `caniuse-lite` (build-time data) | Attribution. |
| Python direct deps (17 + 2 extras) | `pyproject.toml` | All permissive (MIT/BSD/Apache/ISC/PSF). |
| GPL/LGPL packages present in the global interpreter but **not** in the lock | PyQt6, comfy-cli, color-matcher, chardet, fpdf2, py7zr, ldap3, lameenc | Not project dependencies; they pollute any audit run against the global interpreter. |
| ~~172 Rust crates unverified~~ | `worldforge/src-tauri/Cargo.lock` | **Resolved 2026-09-13:** CI `licenses` job (`scripts/license_report.py`, clean environment) covers all 538 crates, 44 Python and 612 npm packages: 0 strong copyleft; weak copyleft = certifi, elkjs, 7 MPL-2.0 crates. |

---

## 13. Contradictions to discuss (brief §7: flag, don't resolve)

1. **Brief: "WorldForge (specced, not built)."** WorldForge is built and tested. Owner ruling
   2026-09-13: the in-repo WorldForge app is "the map tool". Open question: is there a larger
   WorldForge spec (e.g. a Cursor prompt in the vault) the brief was referring to? The vault
   was unreachable during this audit.
2. **Brief Phase −1 bug list** describes bugs already fixed — the list predates the current tree.
   Replaced with audit-found breakages (§2).
3. **`docs/design/EPITAPH_LESSONS.md`** proposes ambient, search, effects and factions as
   core engine/`RoomModel` features. Much of that was built that way. The brief says
   world-specific mechanics are plugins. Either the Epitaph doctrine is engine-level design the
   brief should adopt (ambient/search/effects are genre-neutral), or it was Fablestar design
   that landed in the core. Phase 1 proposes a split; this needs an owner conversation.
4. **`docs/architecture.md` "no in-process LLM inference"** vs the shipped embedded llama backend
   (`sf/agents/embedded_llm.py`, `pyproject` extra `agents-embedded`). A decision was reversed
   without updating the doc.
5. **`CLAUDE.md` "don't mock the database"** vs the hermetic suite built on `tests/fakes.py`.
   Also a quietly reversed decision; matters for how Phase 2+ tests are written.
6. **`README.md:40` WorldForge "write-through via forge API"** vs `CLAUDE.md` (direct disk
   writes) — the code agrees with CLAUDE.md.
7. **Brief decision 2 (no `world_id` columns) vs "switching worlds is a config change plus a
   restart" (§9).** On one database, switching worlds would mix both worlds' characters and
   Nexus overrides. Phase 1 proposes one database per world.

---

## 14. Open items

- **Obsidian vault cross-check** — the vault MCP was unreachable (Obsidian not running). Needed
  for: contradiction 1, whether glyphs/ships/galaxy are part of Fablestar's intended design
  (decides "delete" vs "plugin content type"), and lore to relocate into the world package.
- **Owner WIP** in the tree (`aipub/rooms/apartment_1..4`, `content/world_backup_*`,
  `.desloppify/`) was left untouched.
- **Clean-venv license audit** and `cargo deny` belong in Phase 2a CI.
