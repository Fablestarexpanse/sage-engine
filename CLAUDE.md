# CLAUDE.md — Fablestar MUD Platform

Developer guide for working with this codebase. Read this before touching game logic.

---

## Project overview

Fablestar is a text MUD engine with an optional LLM narration layer. The core game is fully deterministic (Python); LLMs only colour the output text. Players connect over WebSocket and type commands. Admins manage the world through a React admin console that talks to the same server.

**Golden rule:** LLMs describe what happened. Deterministic code decides what happens.

**Philosophy:** Sub-second hot reload on content (YAML) and commands (Python). Change a room description or add a command without restarting the server.

---

## Repository layout

```
src/fablestar/          Python server (Nexus)
  app.py                Global singleton (app_instance)
  server.py             FablestarServer class — owns all subsystems
  __main__.py           Entry point: asyncio.run(run_server())
  admin/                FastAPI REST + WebSocket admin API (NexusApp + routes/)
  commands/             MUD command handlers (@command decorator)
  core/                 Config, TickManager, security (JWT secret), TOML persist
  comfyui_client.py     ComfyUI image-generation client
  hot_reload.py         HotReloader (inotify/watchdog)
  llm/                  LLM client, prompt rendering, output validation
  network/              WebSocketProtocol, Session state machine
  parser/               Tokenizer + CommandDispatcher
  proficiencies/        Conduit proficiency catalog, registry, engine
  services/             EconomyService, PlayerService, SceneService, play tokens
  state/                Redis (hot state), Postgres (persistent), ORM models
  world/                ContentLoader, world Pydantic models, EntitySpawnManager

admin-ui/               React admin console (Vite, port 5174)
player-ui/              React player client (Vite, port 5173)
worldforge/             Tauri desktop WorldForge editor
worldforge-mcp/         MCP server exposing map-building tools (mcp__worldforge__*)
content/world/          Game content (YAML — gitignored changes hot-reload)
  galaxy.yaml           Galaxy definition (systems index)
  entities/             Entity templates (NPC/mob definitions)
  items/                Item templates
  ships/                Ship templates
  systems/              Star system definitions
  zones/                Game zones
    {zone_id}/
      zone.yaml         Zone metadata
      rooms/            Room YAML files; file stem = room slug
  stamps/               WorldForge copy-paste stamp data (editor only, not loaded by server)
prompts/                Jinja2 prompt templates (*.j2)
config/                 TOML config files (gitignored; copy from *.example.toml)
scripts/                Admin bootstrap and maintenance scripts
tests/                  pytest test suite
alembic/                Database migration scripts
```

---

## Startup lifecycle

```
__main__.py
  └─ run_server()
       └─ FablestarServer.start()
            ├─ load_config()            config/ TOML files merged
            ├─ PostgresState.init()     SQLAlchemy async engine + sessionmaker
            ├─ RedisState.init()        redis[hiredis] connection pool
            ├─ ContentLoader init       content_dir="content" (lazy, cached)
            ├─ LLMClient + PromptManager
            ├─ SessionManager
            ├─ EntitySpawnManager
            ├─ CommandDispatcher        imports all commands/  modules → registry
            ├─ PersistenceManager       subscribes to tick events
            ├─ HotReloader              watches content/ and commands/
            ├─ NexusApp (FastAPI)       admin REST + /play WebSocket
            └─ TickManager.start()      4 Hz game loop
```

`app.py` holds the global singleton `app_instance: Optional[FablestarServer]`. Command handlers import it lazily:

```python
from fablestar.app import app_instance  # import inside handler, not at module top
```

---

## Game loop (TickManager)

- **Rate:** 4 Hz (0.25s tick) — configurable via `tick_rate` in `server.toml`
- **Drift compensation:** measures elapsed time and skips ticks if behind
- Publishes `"tick"` event on the `EventBus`
- `PersistenceManager` subscribes and flushes Redis → Postgres every 240 ticks (~60 s)
- `EntitySpawnManager` runs per-tick respawn logic

---

## State architecture

| Concern | Store | Location |
|---|---|---|
| Player location | Redis | `player:loc:{player_id}` |
| Player stats / inventory | Redis | `player:stats:{player_id}`, `player:inv:{player_id}` |
| Room occupants | Redis | `room:players:{room_id}`, `room:entities:{room_id}`, `room:items:{room_id}` |
| Entity live state | Redis | `entity:state:{entity_id}` |
| Item live state | Redis | `item:state:{item_id}` |
| Account / Character records | Postgres | `accounts`, `characters` tables |
| Admin staff | Postgres | `admin_staff` table |
| Scene images | Postgres | `account_scene_images` table |

`RedisState` (`state/redis_client.py`) has typed async methods for every key pattern — use them; don't hand-craft keys.

`PersistenceManager.flush_all()` copies live Redis player state back into the Postgres `characters` row every ~60 s and on server shutdown.

---

## Adding a MUD command

1. Create or edit a file in `src/fablestar/commands/`.
2. Decorate with `@command`:

```python
from fablestar.commands.registry import command
from fablestar.network.session import Session

@command("greet", aliases=["hi", "hello"])
async def greet(session: Session, args: list[str]):
    """Greet another player. Usage: greet <name>"""
    from fablestar.app import app_instance   # lazy import — required pattern
    target = " ".join(args) or "the room"
    await session.send(f"You wave to {target}.")
```

3. Import the module in `server.py` (under the other command imports) so it registers at startup — or rely on HotReloader if adding during a running session.

**Registry:** `commands/registry.py` holds a global `registry: CommandRegistry`. The `@command` decorator registers at import time. Commands receive `(session, args)` — `args` is a lowercased list of tokens after the verb.

**Session state:** `session.player_id` (str), `session.character_id` (str), `session.state` (`SessionState` enum). Check `session.state == SessionState.PLAYING` before accessing player state.

---

## Adding world content

### Room

Create `content/world/zones/{zone_id}/rooms/{room_slug}.yaml`:

```yaml
id: "my_zone:room_slug"     # must match zone_id:file_stem
zone: my_zone
name: The Corridor
type: chamber                # chamber | corridor | hub | exterior
depth: 2
description:
  base: "A dimly lit corridor."
exits:
  north:
    destination: "my_zone:next_room"
    description: "A door to the north."
features:
  - id: console
    name: old terminal
    keywords: [terminal, console]
    description: "Covered in dust."
entity_spawns:
  - template: stalker
    chance: 0.4
    max_count: 1
tags: [lit]
```

The server loads rooms on first access (`ContentLoader.get_room(room_id)`). HotReloader invalidates the cache on file change.

### Entity template

Create `content/world/entities/{id}.yaml`. See `world/models.py` → `EntityTemplate` for the full schema.

### Item template

Create `content/world/items/{id}.yaml`. See `world/models.py` → `ItemTemplate`.

---

## LLM narration flow

Narration is **optional and fire-and-forget** — the game never blocks on LLM output.

```
Command handler
  └─ app_instance.prompt_manager.render("template_name", **context)
       └─ Jinja2 renders prompts/{template_name}.j2
  └─ app_instance.llm_client.generate(prompt, max_tokens=N)
       └─ POST to LM Studio / Ollama / OpenAI-compatible endpoint
  └─ app_instance.llm_client.validator.sanitize(response)
       └─ strips unsafe content, trims to max length
  └─ session.send(narration)
```

Prompt templates live in `prompts/`. Each `.j2` file receives named variables. If the LLM call fails, command handlers fall back to a plain-text message — see `commands/combat.py` for the pattern.

**LLM client config:** `config/llm.toml` (optional). Defaults to disabled. Set `base_url`, `model`, `enabled = true`.

---

## Proficiency system (Conduit)

Proficiencies are organised as dot-path trees, e.g. `combat.melee.blades`. Five stats gate advancement: **FRT** (fortitude), **RFX** (reflex), **ACU** (acuity), **RSV** (resolve), **PRS** (presence).

| File | Role |
|---|---|
| `proficiencies/models.py` | Pydantic models: `ProficiencyLeafDefinition`, `ProficiencyNode`, `ProficiencyCatalogDocument` |
| `proficiencies/registry.py` | `ProficiencyRegistry` — in-memory tree built from catalog |
| `proficiencies/catalog_loader.py` | Loads `content/proficiencies/**/*.yaml` into registry |
| `proficiencies/engine.py` | `ProficiencyEngine` — `try_field_gain()`, XP math, level-up |
| `proficiencies/state_helpers.py` | `ensure_proficiency_block()`, `combat_attack_defense_from_stats()` |
| `proficiencies/tick.py` | Per-tick passive drain / decay |
| `proficiencies/bonus.py` | Stat bonus calculation from proficiency levels |
| `proficiencies/data/` | Built-in proficiency domain definitions (combat, traversal, etc.) |

Hybrid mode (`proficiency_combat_hybrid = true` in `server.toml`) blends legacy stat-based and proficiency-based damage. Disable once proficiencies are fully populated.

**Current status:** The flag defaults to `true` because several combat sub-domains are missing leaf definitions. Once all 12 domains have full leaf coverage and in-game skill usage has been validated, flip the flag to `false` and remove the legacy stat path from `proficiencies/state_helpers.py:combat_attack_defense_from_stats`. Track completion as a milestone before 1.0.

---

## Admin console (Nexus)

The FastAPI app (`admin/nexus.py`, `NexusApp`) mounts all admin routes. Authentication uses JWT HS256 via `NexusAdminAuthMiddleware` — all admin routes require a valid Bearer token unless `admin_auth_required = false` (dev-only).

WebSocket admin connections use a **first-message auth envelope**: after accepting, the server waits up to 10 s for `{"type": "auth", "token": "<jwt>"}` before proceeding. Tokens must never appear in URLs.

Rate limits (via `slowapi`): login endpoints 10 req/min, register 5 req/min.

Key admin modules:
- `admin/nexus.py` — FastAPI app shell (middleware, WebSockets); routes live in `admin/routes/` domain routers (admin_ops, content, world, forge, play, llm_comfyui)
- `admin/admin_security.py` — JWT middleware, `jwt_secret_for_server()`
- `admin/staff_service.py` — admin staff CRUD
- `admin/player_accounts.py` — player account management
- `admin/world_live.py` — live world state queries
- `admin/content_browser.py` — YAML content browsing
- `admin/host_metrics.py` — server health metrics

---

## Configuration

Config files in `config/` are merged at startup. Live files are **gitignored** — copy from `*.example.toml`:

```bash
cp config/server.example.toml config/server.toml
cp config/database.example.toml config/database.toml
```

Important `server.toml` keys:
- `admin_auth_required = true` — default; never disable on a networked host
- `admin_jwt_secret` — must be set when auth is required; generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `cors_origins` — list of allowed origins (default: localhost dev ports)
- `proficiency_combat_hybrid` — blends old stat combat with proficiency system

Environment overrides: `FABLESTAR_` prefix, double-underscore nesting, e.g. `FABLESTAR_SERVER__WEBSOCKET_PORT=8001`.

---

## Development setup

```bash
# 1. Start backing services
docker compose up -d redis postgres

# 2. Run migrations
python -m alembic upgrade head

# 3. (Optional) Bootstrap head admin
python scripts/bootstrap_admin.py --username admin --password 'your-password'

# 4. Start game server
python -m fablestar

# 5. Start admin UI (new terminal)
cd admin-ui
VITE_API_BASE=http://localhost:8001 VITE_WS_BASE=ws://localhost:8001 npm run dev -- --port 5174 --host

# 6. Start player UI (new terminal)
cd player-ui
VITE_NEXUS_PORT=8001 npm run dev -- --port 5173 --host
```

Default ports: Nexus 8001, player UI 5173, admin UI 5174, Postgres 5432, Redis 6379.

---

## WorldForge content editor

WorldForge is a Tauri desktop app (`worldforge/`) for visually editing zones and rooms. It exports content directly into `content/world/`. Stamps (reusable room groups) are saved to `content/world/stamps/`.

**Known issue:** WorldForge historically wrote exports to a nested `content/world/content/world/` path due to a root path misconfiguration. If you see a `content/world/content/` subtree appear after a WorldForge export, the room YAMLs must be moved to `content/world/zones/{zone_id}/rooms/` and the duplicate tree removed. This was corrected manually; check the WorldForge content root setting if it recurs.

### How WorldForge saves (and the conflict risk)

WorldForge does **not** save through the Nexus HTTP API. Its `saveRoomFile()` (`worldforge/src/editors/ZoneEditor.jsx`) calls the Tauri `write_file` command (`worldforge/src-tauri/src/commands.rs`) and writes room YAML **directly to disk**; the server's `HotReloader` then notices the file change and invalidates the content cache. The admin-ui World Builder, by contrast, writes through Nexus (`PUT/POST/DELETE /content/zones/{zone}/rooms/*` in `admin/routes/content.py`).

Because these two paths are unsynchronized, running both editors on the same zone risks last-write-wins clobbering. The `/content/*` room-write routes accept an optional `expected_mtime` (returned by the room-read endpoints) and reject with **409 `content_modified`** when the file changed on disk since it was loaded — the admin-ui builder sends it; direct WorldForge disk writes bypass this guard entirely, so avoid editing the same zone in both tools at once.

There is a **third writer**: `worldforge-mcp/server.py` (the MCP server behind the `mcp__worldforge__*` tools) also reads and writes room YAML and `.positions.json` directly to disk (`_read_room`/`_write_room`/`_write_positions`), with no `expected_mtime` guard — same accepted last-write-wins risk as the Tauri app. Treat any two of the three writers (admin-ui Builder, WorldForge Tauri app, worldforge-mcp tools) editing the same zone concurrently as unsafe.

Related Nexus endpoints (available for HTTP write-through, e.g. the forge chat deploy flow):

- **`POST /forge/inject`** — write a room YAML. Body: `{id: "zone_id:room_slug", yaml_content: "..."}`. Requires the `forge` tool permission and `may_write_zone(zone_id)`. Both `zone_id` and `room_slug` are validated against `^[a-zA-Z0-9_-]+$` (no path traversal). Returns `{status: "success", path: "..."}`.
- **`POST /forge/generate`** — LLM-generate a room YAML draft from a natural-language prompt.

Zone write permissions are controlled by `AdminStaff.permissions.zones` — `["*"]` means all zones, an explicit list restricts to those zone IDs.

---

## Database migrations

Alembic manages schema: `alembic/versions/`. After changing SQLAlchemy models in `state/models.py`:

```bash
python -m alembic revision --autogenerate -m "describe change"
python -m alembic upgrade head
```

---

## Testing

```bash
pytest tests/
```

Tests cover config loading, command dispatch, proficiency math, admin auth, and session state. Integration tests expect a live Postgres (use Docker). Do not mock the database — mocked tests have masked real migration failures in the past.

---

## Key patterns to follow

- **Lazy `app_instance` imports inside handlers** — avoids circular imports at module load time. Always import from `fablestar.app` inside the function body.
- **Never block the game loop** — all game code is `async`. Network I/O, DB queries, and LLM calls must be `await`-ed.
- **LLM failures are non-fatal** — wrap every LLM call in `try/except` and provide a plain-text fallback.
- **Redis for speed, Postgres for durability** — update Redis immediately; PersistenceManager handles the Postgres write asynchronously.
- **Room ID format** — always `zone_id:room_slug`. The slug is the YAML file stem.

---

## rexyMCP architect/executor workflow

This project uses the rexyMCP architect/executor workflow; the contract lives in
REXYMCP.md, imported below.

@REXYMCP.md
