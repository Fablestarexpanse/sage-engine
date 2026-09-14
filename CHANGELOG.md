# Changelog

## Release process — record the publish date

SAGE is licensed under `FSL-1.1-ALv2` (`engine/LICENSE`). Each version converts to the Apache
License 2.0 on the **second anniversary of the date that version is made available**, so every
release entry must record that date. The date is part of the licence terms, not bookkeeping.

For every tagged release:

0. On the release branch, remove the development-only passwordless logins:
   `python scripts/release_check.py --strip`, then run the tests and client builds and commit.
   `python scripts/release_check.py` must exit 0 on the commit you tag (`docs/dev/DEV_AUTH.md`).
1. Add a section headed `## [<version>] — published YYYY-MM-DD`, using the date the version is
   first made available to anyone outside the licensor (push of a public tag, package upload,
   or delivery to a customer, whichever comes first). A private internal tag is not publication.
2. Add the line `Apache-2.0 conversion date: YYYY-MM-DD` (publish date plus two years).
3. Tag the commit `v<version>` and use the same publish date in the tag message.
4. Never edit a recorded publish date after release.

Versions built before the first publication have no conversion date.

## [Unreleased]

- **Search everything (Ctrl+K or /)** from any console page. It covers pages, characters,
  accounts, rooms, items, creatures and lexicon lines, and shows only the kinds the staff member
  has the tool for (`GET /admin/search`). Arrow keys move through results and Enter opens one.
- **"Used by" on every room, item and creature** (`GET /content/references/{rooms,items,entities}/{id}`):
  - **Named in content:** every content field that names the record. This includes exits, spawn
    entries, loot, and fields added by plugins, such as shop stock, recipes and scraps. It finds
    them by matching the id, with no list of plugin fields to maintain.
  - **Saved characters:** who carries an item, and who is saved in a room.
  - **Live state:** copies lying on floors, live creatures by room, and who is in a room now.

  Every entry links to its record. `#/lexicon/<key>` opens a lexicon line.
- **The admin console handles large worlds.**
  - **Items and Creatures tables:** each is one searchable, sortable, paged table
    (`GET /content/templates/{items,entities}`). The columns come from the template model and
    the fields this world's plugins add, such as `attack`, `slot`, `heal`, `recipe`, and each
    creature stat.
  - **Content files are cached:** a file is parsed only when it changes. With 5,000 item
    templates, the first listing took 0.64 s and later listings took 0.16 s. The first listing
    runs in a thread, so it does not stall the game loop.
  - **Accounts** search, filter (suspended, GM, no characters), sort (last sign-in, newest,
    most characters) and page in the database. Before, the list loaded every account and ran
    one count query per account.
  - **Characters** filter by zone and by online or offline, and page.
  - **Record addresses:** `#/content/items/<id>`, `#/content/creatures/<id>`,
    `#/content/rooms/<zone>/<room>`, `#/characters/<id>` and `#/accounts/<id>` each open that
    record.

  Breaking for API clients: `GET /admin/player-accounts` and `GET /admin/characters` now return
  `{rows, total}`.
- **Fixed: staff moving an offline character put it in the room.** The character tools (and the
  account editor's character save) added a character who was not connected to the room's player
  set, so everyone in that room saw it standing there. Offline characters now get only their
  location. Live world shows names already left behind like this and clears them.
- **Live world shows what is really there.** The page now shows:
  - who is in each room, split into players, agents, and names left behind
  - every live creature, including creatures in rooms nobody is standing in (the list used to
    look only in rooms with a connected session)
  - every item lying on a floor, with removal
  - creatures and items in rooms that are not in the world, marked so they stand out

  New routes: `GET /world/items`, `DELETE /world/rooms/{zone}/{room}/items/{item}`,
  `POST /world/occupants/clear-offline`. `GET /world/entities` returns `{rows, total}`.
- **Who's online lists agents**, marked as agents (`GET /players?include_agents=true`).
- **Admin console menus are grouped by staff job:** Overview, Live, Players, World, Economy,
  NPCs, System. Players & sessions is split into Who's online, Characters and Accounts
  (`#/accounts/<id>` opens one account). Live world holds the Redis snapshot and creature
  spawn/despawn, which used to sit in Operations and the Content Library. Operations is now
  Broadcast & reload. AI art credit prices have their own page under Economy. The agent brain
  model settings moved from the Agents page to Server & AI models, and tick metrics moved there
  too. Old `#/players` links still work.
- **Removed: Nexus no longer creates zones or rooms.** `POST /content/zones` and
  `POST /content/zones/{zone}/rooms` are gone, along with the New Zone and Add Room buttons.
  WorldForge is the only room editor. The `locations` and `settings` staff tools no longer exist,
  because nothing checked them.
- **Role presets on Team & access:** Builder, Game master, Moderator and Operator fill in the tool
  ticks (`GET /admin/staff/tool-presets`). Stored permissions are still per tool.
- **Fixed: admin character edits were undone within a minute.** Saving a character in the
  account editor wrote Postgres only. Redis keeps a character's live state after logout, and the
  persistence flush copies it back to Postgres every ~60 s, so the old room and stats returned.
  Character edits now write the live state too.
- **Character tools** (Players & sessions): find a character by name or account, move them to a
  room (unknown rooms refused), set a currency balance, give or remove items, and kick a connected
  player. A connected player is told what staff changed.
- **Account suspension:** a suspended account cannot sign in or get a play token, and its
  characters are disconnected. A wrong password still reads as invalid credentials, so suspension
  is not revealed to someone guessing.
- **Audit log** (System, `team` or `operations` tool): every successful staff write through the
  console is recorded with who, what route, target and body. Passwords, tokens and secrets are
  stored as "(changed)". Needs migration `s2t3u4v5w6x7` (`python -m sage db upgrade`).
- **Fixed: entity and item template YAML routes never worked.** `GET` and `PUT
  /content/{entities,items}/{id}/yaml` returned 422 on every call. The tool check was a postponed
  annotation FastAPI could not resolve, so it became a required query parameter. AI Forge's Deploy
  for entity and item templates used the same routes, so it had never saved anything.
- **Template saves are validated:** the YAML must parse, match the entity or item template fields,
  and keep its id. Otherwise the save is refused with the reason, and nothing is written.
- **Content Library:**
  - **Rooms:** select one to see its description, exits (linked to the rooms they lead to), features,
    spawns, plugin fields, who and what is in it now, its content check findings, and its YAML
    (`GET /content/rooms/{zone}/{slug}`).
  - **Entities:** lists every template on disk, with how many rooms spawn it, instead of only
    spawned ones.
  - **Entities and Items:** open a validated YAML editor.
  - **Dashboard count:** "Entity templates" counts template files.
- **Team & access:** existing staff can be edited (display name, role, zones, tools, new password).
  Tools are grouped and named like the sidebar.

- **Admin console navigation is grouped:** Overview, World, Players, Plugins, AI and System. Plugin pages sit under Plugins.
- **One live sessions table:** it is on Players & sessions; the Dashboard shows a one-line summary and Operations no longer repeats it.
- **Settings removed:** the empty page is gone; the theme toggle stays in the sidebar.
- **Renamed:** Server is now "Server & AI models".

- **Admin console: World & plugins page.**
  - **World package:** its name, id, version, path and room types.
  - **Content check:** the same check as `sage validate` (errors, warnings, notes), run from the console.
  - **Migrations:** status for core and every enabled plugin.
  - **Plugins:** each one with version, source, dependencies, what it registered and what its
    manifest declares, plus a link to its admin page.
  - **AI slots:** each one on or off.
  - **New route:** `GET /admin/world/check`.

- **Admin console shows what is really running.** New `GET /admin/world`: engine version, the running
  world (id, name, version, room types), loaded plugins (version, where they live, what they
  registered), AI slot status, and players and agents online, counted apart. The Dashboard uses it:
  - it names the world and the engine version
  - it lists the loaded plugins where the fake topology diagram used to be
  - it warns while passwordless dev logins are on
- **Live Activity works:** server log lines at WARNING and above stream to the Dashboard.
- **AI Forge only offers what it can deploy:** rooms, entity templates and item templates, using the
  world's own room types. Its cards are disabled when the world has no Forge template, and Accept
  refuses a room that names undeclared types or directions or leads nowhere (422, nothing written).
- **Removed or corrected untrue UI:**
  - the hardcoded `v0.4.1-dev` label, and the Adaptive and Level columns nothing filled
  - the "not authenticated" Operations banner
  - a Restart button that only showed an alert
  - the Skills page's pointers to a moved file and a missing menu
  - the hardcoded "px" bundle suffix
- **Admin pages:**
  - the LLM form offers the embedded backend
  - Agents and Shops use the plugin admin URL the server provides
  - the open page is in the URL, and the tab title names it

- **Tutorial 1, run the engine** (`docs/tutorial/01-run-the-engine.md`): from `git clone` to
  walking the demo world and changing a room while the server runs, with what each quickstart step
  did and how to recover from a broken room file.

- **Nexus serves the built player client at `/`**, so a new install needs one terminal: open
  http://localhost:8001/. `sage quickstart` builds the client when it is missing or older than its
  sources (`--no-client` skips it). A client build now talks to the origin it was loaded from;
  builds hosted elsewhere set `VITE_NEXUS_URL` (they used to assume `127.0.0.1:8001`).

- **`sage quickstart`:** one command from a fresh checkout to a running server. It writes any
  missing config with a generated database password and JWT secret, starts Postgres and Redis with
  Docker Compose, creates the world's database, migrates and runs the server (the SAGE Demo world by
  default). Re-running it changes nothing already done; `--world`, `--no-docker`, `--no-server`.
- **`sage db create`** creates the configured database if it is missing.

- **SAGE Demo world.** `worlds/demo/` ships four rooms around a hub with no plugins, and
  `config/server.example.toml` now runs it instead of Fablestar Expanse. It is licensed with the
  engine.
- **The server refuses to start without a JWT secret** while `admin_auth_required` is on. Before,
  it started and reported healthy, and the first registration or login returned HTTP 500. The
  README quick start now generates the secret.

- **Breaking: database defaults are now `sage`.** `config/database.toml` without `database` or
  `user` now connects to database `sage` as user `sage` (was `fablestar`), and
  `docker-compose.yml` creates `sage`/`sage` unless `.env` sets `POSTGRES_DB` and
  `POSTGRES_USER`. Migration for an existing setup: set `database = "fablestar"` and
  `user = "fablestar"` in `config/database.toml` (or `SAGE_DATABASE__DATABASE` /
  `SAGE_DATABASE__USER`), and add `POSTGRES_DB=fablestar` and `POSTGRES_USER=fablestar` to `.env`.
  Compose only applies those names when the data volume is first created, so existing data keeps
  its names either way.
- **Deprecation end date:** the `FABLESTAR_` environment-variable prefix and the `fablestar`
  console script are removed in **0.3.0**. Rename variables to `SAGE_` and run `sage` or
  `python -m sage`. The server's deprecation warning names the version.
- **Licensing:** first-party plugins (`plugins/`) are licensed FSL-1.1-ALv2 (`plugins/LICENSE`);
  before, they had no license. `NOTICE` is rewritten for the tree as it is, and
  `scripts/notice_check.py` fails CI when a top-level path or world package is missing from it.
  Fablestar Expanse is planned to move to a private repository
  (`docs/sage/FABLESTAR_PRIVATE_REPO_PLAN.md`).
- **Docs and tooling:** `docs/architecture.md` is the canonical architecture document (the pre-SAGE
  one is `docs/dev/ARCHITECTURE_PRE_SAGE.md`); `CLAUDE.md` keeps only agent conventions. Local
  agent tooling files (`rexymcp.toml`, `REXYMCP.md`, `.desloppify/`) are no longer tracked.

- **Development-only passwordless logins, removable for release.** With `dev_mode` and
  `dev_login`, loopback clients can open the player character chooser or sign in to the admin
  console as a head admin without a password, besides the existing named test character. A
  request relayed for a network client is refused, including browsers elsewhere on the LAN that
  reach the Vite dev server through `--host` (the dev proxies now forward client addresses). Every piece is marked, and `scripts/release_check.py`
  lists it (exit 1) or strips it (`--strip`); the live world smoke tests now register real
  accounts, so they pass without it.

- **SAGE decoupling complete** (merged 2026-09-14, PRs #7–#12; repository now
  `Fablestarexpanse/sage-engine`). The engine (`engine/src/sage`) runs world packages
  (`worlds/fablestar`, `worlds/rivermoot`) and first-party plugins (`plugins/`) through a sealed
  plugin API. Every Fablestar mechanic is now a plugin, player text goes through the lexicon, AI
  prompts, style and ComfyUI graphs belong to the world, and Redis keys are namespaced per world.
- **Rivermoot**, the second reference world: 30 rooms, three attributes, silver, levels, ten
  plugins, text-only AI; it boots and plays in CI on the same engine code as Fablestar.
- **Schema (one-way migrations):** character state is JSONB; wallet balances live in stats;
  `echo_credits` became `ai_credits`; `digi_balance`, `reputation` and the retired agent table
  are dropped. Run `python -m sage db upgrade` (core and plugin branches).
- **Tools:** `python -m sage validate` and `python -m sage schema export`; WorldForge reads the
  world's room types, directions and slots and edits plugin fields through generated forms;
  worldforge-mcp validates with the engine linter. The admin World Builder and the
  glyph/galaxy/ship/system surfaces were removed.
- **Clients:** world theme (`ui/theme.yaml`), server-sent command autocomplete, attribute
  point-buy at character creation, plugin admin pages shown only when enabled, credit bundles
  in `comfyui.toml`. Zones without editor layout draw their map from exits.
- Licensing: SAGE engine licensed under FSL-1.1-ALv2 (`engine/LICENSE`); Fablestar Expanse
  content declared proprietary (`NOTICE`). Replaces the undeclared MIT entry in
  `pyproject.toml`.
- SAGE decoupling Phase −1: admin World Builder saves no longer erase WorldForge floors; tick
  handler errors are logged; hot reload drops removed commands.

## [0.2.0] — not published

Pre-SAGE Fablestar MUD platform. Internal version only; never made available, so no conversion
date applies.
