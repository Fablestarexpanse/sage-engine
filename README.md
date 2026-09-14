# Fablestar MUD Platform

> **SAGE decoupling in progress (2026-09-13).** The brief `docs/sage/BRIEF.md`, the rulings log
> `docs/sage/DECISIONS.md` and the approved (2026-09-13) `docs/sage/PHASE1_CONTRACTS.md` take precedence
> over this file, which still describes the pre-split Fablestar-only shape. Audit:
> `docs/sage/PHASE0_AUDIT.md`.

[![Repository](https://img.shields.io/badge/GitHub-sage--engine-181717?logo=github)](https://github.com/Fablestarexpanse/sage-engine)

A sci-fi MUD engine built for rapid iteration: deterministic Python game logic, optional local-LLM narration, AI-generated character portraits and scene art, and a desktop map editor for building the world visually.

**Golden rule:** LLMs describe what happened. Deterministic code decides what happens.

## Screenshots

### Player client

![Fablestar player client — MUD terminal with character sheet, portrait, and AI scene art](docs/screenshots/player-client.png)

### WorldForge map tool

![WorldForge — visual zone editor with room graph, exits, and stamp tools](docs/screenshots/worldforge-map-tool.png)

## What's new

### 2026-09 — Score target reached + WorldForge health pass

- **Server strict health score 85.6/100** (desloppify target 85) — four fix rounds off a 20-dimension review panel: explicit LLM failure contract (`LLMGenerationError`), per-entity combat locking, atomic writes across every content writer, optimistic-concurrency guard extended to room deletes, staff-route auth dependencies, config/security modules consolidated under `core/`.
- **Test suite 104 → 150** — first coverage for the admin HTTP layer (auth middleware, permissions, 409 conflict guards, moderation endpoints), the Redis→Postgres durability write, staff lockout guards, the credit economy, and combat narration fallbacks.
- **Admin console audit fixes** — navigation consolidated into a Content Library, live error banners with auto-recovery, real spawn/despawn wiring.
- **WorldForge health pass** — its own desloppify baseline (79.7), full audit (`docs/dev/WORLDFORGE_AUDIT.md`), the MCP `create_room` crash and reference-image loss fixed, the nested `content/world` scaffold bug closed, live-watch no longer clobbers unsaved edits, and a new vitest suite (27 tests).

### 2026-07 — Code health overhaul (`desloppify/code-health`)

- **Play session tokens** — login now issues a JWT; the client stops re-sending the password on every action and on the game WebSocket.
- **Service architecture** — the server core was split into focused services (economy, player accounts, scene/image generation) and the admin API into six domain routers; the two largest files shrank from ~1,400 and ~1,700 lines to ~500 and ~230.
- **Test suite 30 → 104** — hermetic tests (no live Redis/Postgres needed) covering the tick loop, sessions, permissions/JWT, LLM output validation, spawning, and full command dispatch flows.
- **Typed state** — TypedDict schemas for all JSON-shaped state, a documented play-protocol module, and a fully clean `mypy` run across the server.
- **Hardening** — path-traversal checks on WorldForge room injection, tool-permission validation at registration time, auth guards replacing test fallbacks in command handlers.

### 2026-04 — 0.2.x feature wave

- **Conduit proficiency system** — dot-path skill trees (`combat.melee.blades`), five gating stats, field/mentored/archive advancement, chargen skill picker, and admin tooling.
- **Security hardening** — staff JWT auth on all admin routes, rate limiting, CORS allowlist, credential rotation, first-message WebSocket auth envelope.
- **WorldForge** — Tauri desktop map editor with room graph, stamps (reusable room groups), and saving that writes room YAML directly to `content/world/` on disk (it does not go through the Nexus API; the server hot-reloads the change).
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
pip install -e "./engine[dev]"
(cd engine/clients/admin-ui && npm install)
(cd engine/clients/player-ui && npm install)

# 2. Create live config from the examples (gitignored)
cp config/server.example.toml config/server.toml
cp config/database.example.toml config/database.toml

# 3. Start backing services and run migrations
docker compose up -d redis postgres
python -m sage db upgrade

# 4. Start the game server (Nexus, port 8001)
python -m sage
```

Then start the UIs in separate terminals:

```bash
# Player client → http://localhost:5173
cd engine/clients/player-ui && VITE_NEXUS_PORT=8001 npm run dev -- --port 5173 --host

# Admin console → http://localhost:5174
cd engine/clients/admin-ui && VITE_API_BASE=http://localhost:8001 VITE_WS_BASE=ws://localhost:8001 npm run dev -- --port 5174 --host
```

On PowerShell, set the env vars first (`$env:VITE_NEXUS_PORT="8001"`) and then run `npm run dev`.

| Service | URL |
|---|---|
| Nexus (API + WebSockets) | `http://localhost:8001` |
| Player UI | `http://localhost:5173` |
| Admin UI | `http://localhost:5174` |

**WorldForge** (map editor): `cd engine/tools/worldforge && npm install && npm run tauri dev` — requires the [Tauri prerequisites](https://tauri.app/start/prerequisites/) (Rust toolchain).

## Configuration

TOML files in `config/` are merged at startup; live files are gitignored — copy from the `*.example.toml` files. Environment variables override with the `SAGE_` prefix and double-underscore nesting (e.g. `SAGE_SERVER__WEBSOCKET_PORT=8001`); `FABLESTAR_` still works for one release.

Key `server.toml` settings:

- `admin_auth_required = true` (default) — all admin routes require a staff Bearer token. Never disable on a networked host.
- `admin_jwt_secret` — required when auth is on; generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
- Optional extras: `llm.toml` (LM Studio / Ollama), `comfyui.toml` (art generation), `redis.toml`.

To create the first head admin: `python engine/scripts/bootstrap_admin.py --username youradmin --password 'a-strong-password'`. Head admins manage additional staff, tool access, and zone permissions from **Team & access** in the admin UI.

Do not expose Nexus directly to the public internet — put it behind a reverse proxy with TLS.

## Project layout

```
engine/        SAGE engine: src/sage (server), tests, alembic, pyproject
engine/clients/admin-ui/          React admin console
engine/clients/player-ui/         React player client
engine/tools/worldforge/        Tauri desktop map editor
worlds/           world packages (Fablestar, Rivermoot): content, lexicon, ai/prompts, plugins
```

Developer documentation lives in [`CLAUDE.md`](CLAUDE.md) (architecture guide) and [`docs/`](docs/).

## License

The SAGE engine is licensed under the Functional Source License, Version 1.1, ALv2 Future License (`FSL-1.1-ALv2`) — see [`engine/LICENSE`](engine/LICENSE) and the plain-English [`LICENSE-FAQ.md`](LICENSE-FAQ.md). Each release becomes Apache-2.0 two years after it is published.

Fablestar Expanse world content, lore, art and branding are proprietary, all rights reserved. [`NOTICE`](NOTICE) lists which paths are which.
