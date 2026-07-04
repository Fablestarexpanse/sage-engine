# Fablestar MUD Platform

[![Repository](https://img.shields.io/badge/GitHub-FablestarExpanseMUD-181717?logo=github)](https://github.com/Fablestarexpanse/FablestarExpanseMUD)

A sci-fi MUD engine built for rapid iteration: deterministic Python game logic, optional local-LLM narration, AI-generated character portraits and scene art, and a desktop map editor for building the world visually.

**Golden rule:** LLMs describe what happened. Deterministic code decides what happens.

## Screenshots

### Player client

![Fablestar player client — MUD terminal with character sheet, portrait, and AI scene art](docs/screenshots/player-client.png)

### WorldForge map tool

![WorldForge — visual zone editor with room graph, exits, and stamp tools](docs/screenshots/worldforge-map-tool.png)

## What's new

### 2026-07 — Code health overhaul (`desloppify/code-health`)

- **Play session tokens** — login now issues a JWT; the client stops re-sending the password on every action and on the game WebSocket.
- **Service architecture** — the server core was split into focused services (economy, player accounts, scene/image generation) and the admin API into six domain routers; the two largest files shrank from ~1,400 and ~1,700 lines to ~500 and ~230.
- **Test suite 30 → 104** — hermetic tests (no live Redis/Postgres needed) covering the tick loop, sessions, permissions/JWT, LLM output validation, spawning, and full command dispatch flows.
- **Typed state** — TypedDict schemas for all JSON-shaped state, a documented play-protocol module, and a fully clean `mypy` run across the server.
- **Hardening** — path-traversal checks on WorldForge room injection, tool-permission validation at registration time, auth guards replacing test fallbacks in command handlers.

### 2026-04 — 0.2.x feature wave

- **Conduit proficiency system** — dot-path skill trees (`combat.melee.blades`), five gating stats, field/mentored/archive advancement, chargen skill picker, and admin tooling.
- **Security hardening** — staff JWT auth on all admin routes, rate limiting, CORS allowlist, credential rotation, first-message WebSocket auth envelope.
- **WorldForge** — Tauri desktop map editor with room graph, stamps (reusable room groups), and write-through saving to the server via the forge API.
- **ComfyUI integration + economy** — AI character portraits and room scene art with a spendable credit balance, gallery, and admin-configurable costs.
- **World Builder** — admin UI for zones, rooms, star systems, and ships backed by a content API.

## Features

- **Deterministic engine** — 4 Hz tick loop, Redis for hot state, PostgreSQL for persistence.
- **Sub-second hot reload** — edit room YAML under `content/` or command handlers in Python without restarting the server.
- **Optional LLM narration** — LM Studio or Ollama colour the output text; every LLM call has a deterministic fallback, so the game runs fine with no model at all.
- **AI art pipeline** — ComfyUI workflows for portraits and scene art, gated by an in-game credit economy.
- **Three frontends** — React player client, React admin console (AI Forge, world tooling, staff roles, live presence), and the WorldForge desktop map editor.

## Quick start

Prerequisites: **Python 3.11+**, **Node.js LTS**, **Docker** (for Redis + PostgreSQL).

```bash
# 1. Install the server and UI dependencies
pip install -e .
(cd admin-ui && npm install)
(cd player-ui && npm install)

# 2. Create live config from the examples (gitignored)
cp config/server.example.toml config/server.toml
cp config/database.example.toml config/database.toml

# 3. Start backing services and run migrations
docker compose up -d redis postgres
python -m alembic upgrade head

# 4. Start the game server (Nexus, port 8001)
python -m fablestar
```

Then start the UIs in separate terminals:

```bash
# Player client → http://localhost:5173
cd player-ui && VITE_NEXUS_PORT=8001 npm run dev -- --port 5173 --host

# Admin console → http://localhost:5174
cd admin-ui && VITE_API_BASE=http://localhost:8001 VITE_WS_BASE=ws://localhost:8001 npm run dev -- --port 5174 --host
```

On PowerShell, set the env vars first (`$env:VITE_NEXUS_PORT="8001"`) and then run `npm run dev`.

| Service | URL |
|---|---|
| Nexus (API + WebSockets) | `http://localhost:8001` |
| Player UI | `http://localhost:5173` |
| Admin UI | `http://localhost:5174` |

**WorldForge** (map editor): `cd worldforge && npm install && npm run tauri dev` — requires the [Tauri prerequisites](https://tauri.app/start/prerequisites/) (Rust toolchain).

## Configuration

TOML files in `config/` are merged at startup; live files are gitignored — copy from the `*.example.toml` files. Environment variables override with the `FABLESTAR_` prefix and double-underscore nesting (e.g. `FABLESTAR_SERVER__WEBSOCKET_PORT=8001`).

Key `server.toml` settings:

- `admin_auth_required = true` (default) — all admin routes require a staff Bearer token. Never disable on a networked host.
- `admin_jwt_secret` — required when auth is on; generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
- Optional extras: `llm.toml` (LM Studio / Ollama), `comfyui.toml` (art generation), `redis.toml`.

To create the first head admin: `python scripts/bootstrap_admin.py --username youradmin --password 'a-strong-password'`. Head admins manage additional staff, tool access, and zone permissions from **Team & access** in the admin UI.

Do not expose Nexus directly to the public internet — put it behind a reverse proxy with TLS.

## Project layout

```
src/fablestar/     Python server — services, admin routers, commands, world loader
content/world/     Game content (YAML) — zones, rooms, entities, items; hot-reloaded
admin-ui/          React admin console
player-ui/         React player client
worldforge/        Tauri desktop map editor
prompts/           Jinja2 templates for LLM narration and forge generation
tests/             Hermetic pytest suite (no live services required)
```

Developer documentation lives in [`CLAUDE.md`](CLAUDE.md) (architecture guide) and [`docs/`](docs/).

## License

MIT — see `pyproject.toml`.
