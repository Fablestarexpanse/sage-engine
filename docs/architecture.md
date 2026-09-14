# SAGE architecture

How the SAGE engine, world packages and plugins fit together, and how to extend each. This is the
canonical architecture document. The contracts behind it are `docs/sage/PHASE1_CONTRACTS.md`
(approved 2026-09-13); every ruling since is in `docs/sage/DECISIONS.md`, and when this file and
those disagree, they win. The pre-SAGE design is kept for the record in
`docs/dev/ARCHITECTURE_PRE_SAGE.md`.

---

## Overview

SAGE is a text-world engine (MUD) with an optional LLM narration layer. The core game is fully
deterministic Python; LLMs only colour the output text. Players connect over WebSocket and type
commands. Staff run the world through the Nexus admin console, which talks to the same server.

Three kinds of code, kept apart on purpose:

- **Engine** (`engine/src/sage`): sessions, parser, tick loop, state, content loading, lexicon,
  wallet, AI plumbing, plugin host. It knows no setting: no world names, no mechanics that only
  one world wants.
- **World packages** (`worlds/<id>`): content, stats, currencies, lexicon, AI prompts and style,
  ComfyUI graphs, UI theme, and world-only plugins. Rivermoot (the reference world, FSL) and
  Fablestar Expanse (proprietary, moving to a private repository) are the two in the repo.
- **Plugins** (`plugins/<id>` first-party, `worlds/<id>/plugins/<id>` world-only): every game
  mechanic (combat, shops, factions, crafting, agents, Conduit proficiencies, levels ...),
  registering only through `sage.api`.

**Golden rule:** LLMs describe what happened. Deterministic code decides what happens.

**Do not add world-specific code to the engine.** Put the term in a world package, the text
behind a lexicon key, the mechanic in a plugin. The invariant ratchet (see Testing) enforces it.

---

## Repository layout

```
engine/src/sage/          SAGE engine package (Nexus server)
  app.py                  Global singleton (app_instance)
  server.py               SageServer — owns every subsystem
  cli.py                  python -m sage [db | plugin | validate | schema]
  api/                    sage.api — the only import surface plugins may use
  plugins/                Plugin loader, manifest seal, host, migrations, uninstall, offline host
  admin/                  FastAPI REST + WebSocket admin API (NexusApp + routes/)
  commands/               Engine commands (look, map, help, say, tell, movement, items, quit)
  core/                   Config, TickManager, EventBus, resolvers, security, TOML persist
  effects/                Timed effects engine (buffs, damage over time)
  lexicon/                Engine default strings (en.yaml), lexicon layers, Nexus overrides
  llm/                    LLM client, AI slots (prompts.py), world style, output validation
  network/                WebSocket protocol, Session state machine, panels, snapshot sections
  parser/                 Tokenizer + CommandDispatcher
  services/               Economy (AI credits), player accounts, scene art, play tokens
  state/                  Redis (hot state), Postgres (persistent), ORM models
  world/                  World packages, content loader, spawner, wallet, chargen, lint,
                          content schema, layout, UI theme, resolver slots
engine/clients/player-ui/ React player client (Vite, port 5173)
engine/clients/admin-ui/  React Nexus admin console (Vite, port 5174)
engine/tools/worldforge/  Tauri desktop WorldForge editor
engine/tools/worldforge-mcp/  MCP server exposing map-building tools (mcp__worldforge__*)
engine/tests/             pytest suite (run from repo root: python -m pytest)
engine/alembic/           Core database migrations (engine/alembic.ini)
engine/scripts/           Admin bootstrap and account scripts
plugins/<id>/             First-party plugins: plugin.toml, sage_plugin_<id>/, lexicon/, migrations/
worlds/<id>/              World packages
  world.toml              id, name, start/respawn rooms, room types, exit dirs, equipment slots,
                          enabled plugins, params
  stats.yaml              attributes, vitals, chargen attribute points
  currencies.yaml         in-world currencies
  content/world/          zones/{zone}/rooms/*.yaml (+ zone.yaml, .positions.json), entities/, items/
  content/<type>/         plugin content types (achievements/, factions/, agents/, proficiencies/ ...)
  lexicon/en.yaml         string overrides
  ai/                     prompts/<slot>.j2, style.yaml, comfyui/*.json
  ui/theme.yaml           player client mark and accent colours
  plugins/<id>/           world-only plugins (Fablestar: conduit, morality; Rivermoot: levels)
  content.schema.json     exported content schema for offline editors
config/                   TOML config files (gitignored; copy from *.example.toml)
scripts/                  Invariant ratchet, denylist, license report
```

---

## Startup lifecycle

```
__main__.py → cli.main() → run_server()
  └─ SageServer.__init__/start()
       ├─ load_config()              config/ TOML files merged, SAGE_ env overrides
       ├─ select_world()             worlds/<server.world> → WorldPackage (world.toml, stats, currencies)
       ├─ engine resolver slots      death, progression, chargen, combat ratings (world-aware defaults)
       ├─ PostgresState / RedisState Redis keys namespaced by world id
       ├─ ContentLoader              the world's content/ (lazy, cached)
       ├─ LLMClient + PromptManager  the world's ai/prompts and ai/style.yaml
       ├─ CommandRegistry            engine command modules
       ├─ PluginHost.load()          discover → validate manifests → topo-sort → refuse pending
       │                             migrations → setup(api) → seal (undeclared touches fail boot)
       ├─ lexicon                    engine defaults < plugin layers < world < Nexus overrides
       ├─ HotReloader                content YAML and engine command modules
       ├─ NexusApp (FastAPI)         admin REST, /play routes, plugin routes, WebSockets
       └─ TickManager.start()        4 Hz game loop
```

`app.py` holds the global singleton `app_instance: Optional[SageServer]`. Engine command handlers
import it lazily:

```python
from sage.app import app_instance  # import inside handler, not at module top
```

---

## Game loop, events and resolvers

- **Tick:** 4 Hz (0.25 s), configurable via `tick_rate` in `server.toml`, with drift compensation.
  Plugins add jobs with `api.tick.every(seconds, fn, name=...)`; a failing job is logged and the
  loop keeps running. `PersistenceManager` flushes Redis → Postgres about every 60 s and at
  shutdown; plugins hook in with `api.persistence.on_flush`.
- **Events** (`core/events.py`): fan-out notifications with no return value (`EntityKilled`,
  `RoomEntered`, `CountersChanged` ...). Subscribers may append player lines to `event.messages`
  and, for events that carry it, change `event.stats`: the publisher saves that blob.
- **Resolver slots** (`core/resolvers.py`, `world/slots.py`): single-provider hooks that return
  values, each with an engine default: `combat.ratings`, `death.check`/`death.respawn`,
  `progression.*`, `chargen.validate`/`seed`/`options`. A world's plugin provides the real one
  (Fablestar: conduit; Rivermoot: levels).

---

## State architecture

| Concern | Store | Location |
|---|---|---|
| Player location | Redis | `<world>:player:{player_id}:location` |
| Player stats / inventory | Redis | `<world>:player:{player_id}:stats`, `<world>:player:{player_id}:inventory` |
| Room occupants | Redis | `<world>:room:{room_id}:players`, `...:entities`, `...:items` |
| Entity live state | Redis | `<world>:entity:{entity_id}:state` |
| Item live state | Redis | `<world>:item:{item_id}:state` |
| Account / Character records | Postgres | `accounts`, `characters` tables (one database per world) |
| Plugin tables | Postgres | `plg_<plugin>_*` |
| Admin staff | Postgres | `admin_staff` table |
| Scene images | Postgres | `account_scene_images` table |

`RedisState` (`state/redis_client.py`) has typed async methods for every key pattern — use them;
don't hand-craft keys. Anything that must build a raw key passes it through `redis.key()`.

The character stats blob (JSONB) holds engine vitals (`hp`, `max_hp`), the world's attributes
(from `stats.yaml`), wallet balances under currency keys, engine counters and effects, and one
block per plugin (`api.state.block`). Plugins change stats only through `api.state.edit`, which
refuses top-level keys that neither they nor any loaded plugin declared.

---

## Adding a command

**In a plugin (the normal case):** register it in `setup(api)` and declare it in the manifest.

```python
# plugins/greeting/sage_plugin_greeting/main.py
from sage.api import PluginAPI


def setup(api: PluginAPI) -> None:
    async def greet(session, args):
        """Greet someone. Usage: greet <name>"""
        target = " ".join(args) or api.t("greeting.nobody")
        await session.send(api.t("greeting.wave", target=target))

    api.commands.register("greet", greet, aliases=["hi"])
```

```toml
# plugins/greeting/plugin.toml
[plugin]
id = "greeting"
name = "Greeting"
version = "1.0.0"
engine = ">=0.2,<0.3"
entry = "sage_plugin_greeting.main:setup"
first_party = true

[touches]
commands = ["greet"]
lexicon_prefix = "greeting."
```

Put the strings in `plugins/greeting/lexicon/en.yaml` and enable the plugin in a world's
`world.toml` `[plugins]` table. Plugin code imports only `sage.api`.

**In the engine** (only for setting-free basics): add a handler in `engine/src/sage/commands/`
with `@command`, send text with `await session.say("lexicon.key", **vars)` and add the key to
`engine/src/sage/lexicon/en.yaml`. A literal `session.send("...")` fails the ratchet, and
`test_every_engine_key_has_an_engine_default` fails a key with no default.

Commands receive `(session, args)`; `args` is the lowercased token list after the verb
(`session.raw_args` keeps the original case). `session.player_id` is the character name.

---

## Adding world content

### Room

Create `worlds/<world>/content/world/zones/{zone_id}/rooms/{room_slug}.yaml`:

```yaml
id: "my_zone:room_slug"     # must match zone_id:file_stem
zone: my_zone
name: The Corridor
type: street                 # one of world.toml [content] room_types
depth: 2
description:
  base: "A dimly lit corridor."
exits:
  north:                     # one of world.toml [content] exit_dirs
    destination: "my_zone:next_room"
    description: "A door to the north."
features:
  - id: console
    name: old terminal
    keywords: [terminal, console]
    description: "Covered in dust."
entity_spawns:
  - template: river_rat
    chance: 0.4
    max_count: 1
tags: [outdoor]
shop:                        # a plugin field (shop plugin); see content.schema.json
  name: the stall
  sells: [{template: bread_loaf, price: 1}]
```

The server loads rooms on first access (`ContentLoader.get_room`); HotReloader invalidates the
cache on file change. Fields plugins add to rooms, features, items and entities are listed with
their schema in the package's `content.schema.json`.

### Entity and item templates

`worlds/<world>/content/world/entities/{id}.yaml` (`world/models.py` → `EntityTemplate`) and
`.../items/{id}.yaml` (`ItemTemplate`, plus plugin fields such as `slot`, `attack`, `heal`).

### Check and export

```bash
python -m sage validate --world <id> [--zone <zone>] [--info]
python -m sage schema export --world <id> --out worlds/<id>/content.schema.json
```

`test_exported_schema_is_current` fails when a plugin's content fields change and the exported
schema was not regenerated.

---

## AI: narration, style and art

Narration is **optional and fire-and-forget** — the game never blocks on LLM output.

```
engine or plugin code
  └─ prompt_manager.render("narrate.room", **context)      # an AI slot
       └─ worlds/<world>/ai/prompts/narrate.room.j2          (SlotDisabled if absent)
  └─ llm_client.generate_or_raise(prompt, max_tokens=N)      # LM Studio / Ollama / OpenAI-compatible
  └─ LLMValidator(style.rules()).sanitize(text)              # world content rules
  └─ session.send(...)                                       # after the deterministic outcome
```

AI slots are declared by the engine (`sage.llm.prompts.ENGINE_SLOTS`: narrate.room, forge.room,
forge.content, image.area, image.portrait, image.scene) and by plugins (`api.ai.slot(name)` →
`<plugin>.<name>`). A world fills a slot with `ai/prompts/<slot>.j2`; an unfilled slot is
disabled and callers take their plain path. `ai/style.yaml` gives templates `{{ style.tone }}`,
the system prompt and the content rules. ComfyUI graphs live in `ai/comfyui/`
(`comfyui.toml` paths override them). See `plugins/combat` (`api.ai.narrate`) for the pattern.

**Config:** `config/llm.toml` (disabled by default), `config/comfyui.toml` (art, AI credit costs,
`[[credit_bundles]]`), `config/agents_llm.toml` (agent characters).

---

## Player client and panels

The player client draws nothing world-specific on its own:

- **World:** `GET /play/world` gives the name and `ui/theme.yaml` (mark, accent colours).
- **Commands:** `GET /play/commands` gives the command names for autocomplete.
- **Character creation:** `GET /play/chargen/options` gives the choices step. Two kinds are rendered: `skill_points` and `attribute_points`.
- **Panels:** plugins declare them with `api.ui.panel(name, kind, section)`. Kinds are key_value, list, stat_sheet, wallet, table and tree. The data comes from snapshot sections they contribute with `api.snapshot.contribute`. There is no plugin-shipped client JS.

---

## Admin console (Nexus)

The FastAPI app (`admin/nexus.py`, `NexusApp`) mounts all admin routes. Authentication uses JWT
HS256 via `NexusAdminAuthMiddleware` — all admin routes require a valid Bearer token unless
`admin_auth_required = false` (dev-only). Staff tools gate routes (`require_tool`).

WebSocket admin connections use a **first-message auth envelope**: after accepting, the server
waits up to 10 s for `{"type": "auth", "token": "<jwt>"}`. Tokens must never appear in URLs.

Rate limits (via `slowapi`): login endpoints 10 req/min, register 5 req/min.

Key modules and routes:
- `admin/routes/` — domain routers: admin_ops, content, world, forge, play, llm_comfyui
- `admin/admin_security.py` — JWT middleware, tool ids, `jwt_secret_for_server()`
- `admin/staff_service.py`, `admin/player_accounts.py` — staff and player account management
- `admin/content_browser.py` — zone/room/template listing and template YAML editing
- Plugins mount admin routers at `/plugins/<id>/admin` behind a tool; `GET /admin/plugin-pages`
  tells the console which plugin pages (skills, agents, shops) the running world has
- `GET /schema/world` — the content schema; `GET /admin/economy` — AI credit settings and bundles

---

## Configuration

Config files in `config/` are merged at startup. Live files are **gitignored** — copy from `*.example.toml`:

```bash
cp config/server.example.toml config/server.toml
cp config/database.example.toml config/database.toml
```

`database.toml` defaults to database and user `sage`, matching `docker-compose.yml`'s defaults
(`POSTGRES_DB` / `POSTGRES_USER` in `.env` override both sides).

Important `server.toml` keys:
- `world` — the world package to run (a directory under `worlds_dir`, default `worlds`)
- `admin_auth_required = true` — default; never disable on a networked host
- `admin_jwt_secret` — must be set when auth is required; generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `cors_origins` — list of allowed origins (default: localhost dev ports)
- `dev_mode` — local development only (seeds test accounts)
<!-- DEV-AUTH:BEGIN -->
- `dev_login` — passwordless logins for local testing (see below); stripped for release
<!-- DEV-AUTH:END -->

World-specific tuning lives in the world's `world.toml` `[params]`, not in `server.toml`
(for example `"conduit.combat_hybrid"`, `"effects.rest_room_types"`,
`"engine.death.respawn_bill_max"`).

Environment overrides: `SAGE_` prefix, double-underscore nesting, e.g. `SAGE_SERVER__WEBSOCKET_PORT=8001`. The pre-rename `FABLESTAR_` prefix is deprecated: it still works in 0.2.x with a warning and is removed in 0.3.0.

---

## Development setup

`sage quickstart` (`engine/src/sage/quickstart.py`) is the one-command path: it writes missing
`.env`, `config/server.toml` (world, JWT secret, `dev_mode`, `dev_login`) and `config/database.toml`,
runs `docker compose up -d redis postgres`, waits for both, creates the world's database
(`sage db create`), runs `sage db upgrade` in a subprocess, builds the player client when its
`dist/` is missing or older than its sources, then the server.

Nexus serves the built player client (`server.player_client_dir`, default
`engine/clients/player-ui/dist`) at `/` from its 404 fallback (`sage.admin.player_client`), so
routes added later, such as plugin routers, are never shadowed. Only GET/HEAD for `/`, `/assets/*`
and root-level files reach it; those paths are public in `is_public_admin_path`, and every API
route keeps its auth. A client build talks to its own origin unless built with `VITE_NEXUS_URL`. The world is `--world`,
else the configured world, else `demo`; any world other than the configured one uses the database
`sage_<world>`. It never changes an existing config file.

By hand:

```bash
# 1. Start backing services (docker compose reads POSTGRES_PASSWORD from the gitignored .env;
#    config/database.toml must use the same password)
docker compose up -d redis postgres

# 2. Create the configured database if missing, then run migrations (core + plugin branches)
python -m sage db create
python -m sage db upgrade

# 3. (Optional) Bootstrap head admin
python engine/scripts/bootstrap_admin.py --username admin --password 'your-password'

# 4. Start game server
python -m sage

# 5. Start admin UI (new terminal)
cd engine/clients/admin-ui
VITE_API_BASE=http://localhost:8001 VITE_WS_BASE=ws://localhost:8001 npm run dev -- --port 5174 --host

# 6. Start player UI (new terminal)
cd engine/clients/player-ui
VITE_NEXUS_PORT=8001 npm run dev -- --port 5173 --host
```

A second world runs beside the first with its own database and port:
`SAGE_SERVER__WORLD=rivermoot SAGE_DATABASE__DATABASE=sage_rivermoot SAGE_SERVER__WEBSOCKET_PORT=8002`
(run `db upgrade` with the same variables first); point a player client at it with
`VITE_NEXUS_PORT=8002`.

<!-- DEV-AUTH:BEGIN -->
**Testing without passwords (development only):** with `dev_mode = true` and `dev_login = true` in `config/server.toml`, loopback clients get passwordless logins (`sage.admin.routes.dev_auth`, details in `docs/dev/DEV_AUTH.md`):
- Player: `POST /play/dev/login {"character": "Qa Tester"}` returns a play token for that character (created on the `dev-login` account if missing; other accounts' characters and agent names are refused); connect the WebSocket with `{"token": ..., "character_id": ...}`. `{"character": ""}` returns a token with no character, so the client opens the chooser (to test character creation). The player UI's sign-in page shows both.
- Staff: `POST /admin/dev/login` returns a head-admin token for the `dev-staff` account (no usable password). The admin console's sign-in page shows a dev login button.
- A proxied request passes only when every forwarded client address is loopback (the Vite dev proxies send `X-Forwarded-For`, so LAN browsers reaching Vite through `--host` are refused). The routes do not exist without both flags. Never enable on a networked host.
- All of it is marked `DEV-AUTH`. Keep new dev-only auth code inside the markers; `python scripts/release_check.py --strip` removes it before a release, and the check fails while any is left.
<!-- DEV-AUTH:END -->

Default ports: Nexus 8001, player UI 5173, admin UI 5174, Postgres 5432, Redis 6379.

---

## WorldForge content editor

WorldForge is a Tauri desktop app (`engine/tools/worldforge/`) for visually editing a world package's zones, rooms, entities and items. Picking the repository root finds `worlds/<id>/content/world`. Room types, exit directions and equipment slots come from the package's `content.schema.json`, and plugin fields get generated forms (room Plugins tab, feature blocks, item plugin fields). Stamps (reusable room groups) are saved to `content/world/stamps/`.

### How WorldForge saves (and the conflict risk)

WorldForge does **not** save through the Nexus HTTP API. Its `saveRoomFile()` (`engine/tools/worldforge/src/editors/ZoneEditor.jsx`) calls the Tauri `write_file` command (`engine/tools/worldforge/src-tauri/src/commands.rs`) and writes room YAML **directly to disk**; the server's `HotReloader` then notices the file change and invalidates the content cache. The admin World Builder that used to write rooms through Nexus was retired in SAGE 3.18 (owner G.6); a Nexus write-through backend for WorldForge is deferred (DECISIONS, 5.8).

The other structural writer is `engine/tools/worldforge-mcp/server.py` (the MCP server behind the `mcp__worldforge__*` tools), which reads and writes room YAML and `.positions.json` directly to disk. Its `validate_zone` is the engine linter (`sage.world.lint`) and its room types come from `world.toml`. Neither writer guards against the other (last write wins), so don't edit the same zone in the WorldForge app and through the MCP tools at the same time.

Related Nexus endpoints:

- **`POST /forge/inject`** — write a room YAML. Body: `{id: "zone_id:room_slug", yaml_content: "..."}`. Requires the `forge` tool permission and `may_write_zone(zone_id)`. Both `zone_id` and `room_slug` are validated against `^[a-zA-Z0-9_-]+$` (no path traversal). Returns `{status: "success", path: "..."}`.
- **`POST /forge/generate`** — LLM-generate a room YAML draft from a natural-language prompt.

Zone write permissions are controlled by `AdminStaff.permissions.zones` — `["*"]` means all zones, an explicit list restricts to those zone IDs.

---

## Database migrations

Alembic manages schema: `engine/alembic/versions/`. The core chain is labelled `sage_core`; plugins with tables ship their own branch (`plg_<id>`, tables `plg_<id>_*`) in `<plugin>/migrations/versions/`. The server refuses to start while any core or enabled-plugin migration is unapplied — run `python -m sage db upgrade` (or `db status` to list them). `python -m sage plugin uninstall <id> [--purge-state]` drops a plugin's tables, optionally its character state, and its `world.toml` entry. After changing SQLAlchemy models in `state/models.py`:

```bash
python -m alembic -c engine/alembic.ini revision --autogenerate -m "describe change"   # core schema only
python -m sage db upgrade
```

---

## Testing

```bash
python -m pytest
```

**Two tiers (owner ruling 2026-09-13, `docs/dev/STANDARDS.md` §3.5):** the default suite is hermetic — `python -m pytest` passes with no services, using in-memory fakes in `engine/tests/fakes.py`. A live tier (`@pytest.mark.live`, run with `SAGE_LIVE_TESTS=1` against Docker Postgres/Redis, required in CI) covers migrations, persistence, plugin install/uninstall, and both reference worlds booting and playing (`test_world_smoke.py`, including Rivermoot's shop/fight/level loop). Never test migrations or persistence against fakes alone — mocked tests have masked real migration failures in the past.

```bash
docker compose up -d redis postgres
SAGE_LIVE_TESTS=1 python -m pytest -m live
```

Live tests create and drop their own `sage_live_*` databases and use Redis db 15, so they never touch the dev database. `engine/tests/live/test_migrations.py::test_models_match_migrations` fails when the ORM models and migrations disagree — fix the model or add a migration, never weaken the test.

First-party plugin tests live in `engine/tests/plugins/`, world plugin tests beside the plugin (`worlds/<id>/plugins/<id>/tests`); both load plugins through the real `PluginHost`. WorldForge: `cd engine/tools/worldforge && npx vitest run`.

**NOTICE check** (`scripts/notice_check.py`, CI licenses job): every tracked top-level path and
world package must be listed in `NOTICE` with its terms, and every path `NOTICE` lists must exist.

**SAGE invariant ratchet** (CI step, `scripts/sage_invariants.py`): counts world-specific terms (`scripts/sage_denylist.toml`) and hardcoded player-facing strings (`session.send("...")`) per engine file, and fails if any file's count rises above `scripts/sage_invariants_baseline.json`. Run `python scripts/sage_invariants.py check` before committing. When you remove hits, run `python scripts/sage_invariants.py update` to lock in the lower counts. Never raise the baseline to make CI pass — put the term in a world package or the text behind a lexicon key instead. The same check enforces the import boundary with zero tolerance: engine code never imports `sage_plugins`/`sage_worlds` (dynamic imports only in the plugin loader and command registry), and plugin code imports only `sage.api`.
