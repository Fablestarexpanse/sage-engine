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
