# Fablestar — Architecture

> **SAGE decoupling in progress (2026-09-13).** The brief `docs/sage/BRIEF.md`, the rulings log
> `docs/sage/DECISIONS.md` and, once approved, `docs/sage/PHASE1_CONTRACTS.md` take precedence
> over this file, which still describes the pre-split Fablestar-only shape. Audit:
> `docs/sage/PHASE0_AUDIT.md`.

> **Status:** Living design doc, pre-SAGE. M1 (Code Quality Foundation) is complete.
> This document is the source of truth for the intended design; the code under
> `src/fablestar/` is the source of truth for what actually runs.

## What Fablestar is

A deterministic text MUD engine with an optional LLM narration overlay.
Players connect over WebSocket and type commands. The engine decides every
outcome (combat, movement, inventory, proficiencies) through pure Python
logic. LLMs only colour the output text — they describe what happened, they
do not decide it.

**Core properties:**
- Sub-second hot reload on content (YAML) and commands (Python) with no
  server restart.
- Deterministic tick loop at 4 Hz; LLM calls are fire-and-forget and never
  block a tick.
- Optional services (LLM narration, ComfyUI image gen) degrade gracefully —
  the engine runs without them.

## The three layers

```
┌─────────────────────────────────────────────────────────────────┐
│ Network / Protocol layer                                          │
│   WebSocket (FastAPI/uvicorn)  ·  SessionState machine            │
│   NexusApp (admin REST + /play WS)                               │
└───────────────────┬─────────────────────────────────────────────┘
                    │ Session (player_id, state, Protocol)
┌───────────────────▼─────────────────────────────────────────────┐
│ Game Engine                                                       │
│   TickManager (4 Hz)  ·  CommandDispatcher                       │
│   CommandRegistry  ·  ProficiencyEngine (Conduit)                │
│   EntitySpawnManager  ·  PersistenceManager                      │
│   [optional] LLMClient + PromptManager  ·  ComfyUI client        │
└───────────────────┬─────────────────────────────────────────────┘
                    │ async reads/writes
┌───────────────────▼─────────────────────────────────────────────┐
│ State / Data                                                      │
│   Redis (hot: player loc/stats/inv, room occupants, entity state) │
│   PostgreSQL (durable: accounts, characters, admin staff, images) │
│   YAML content (rooms, entities, items, ships, systems — hot-     │
│     reload via HotReloader/watchdog → ContentLoader cache bust)  │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 1 — Network / Protocol

Entry point is `__main__.py → run_server() → FablestarServer.start()`.

The server mounts a FastAPI app (`NexusApp`) on uvicorn. Two connection types:

- **`/play` WebSocket** — player game connections. Each connection becomes a
  `Session` (uuid, Protocol, `SessionState`). The `WebSocketProtocol`
  implements `Protocol` (abstract send/close/peer_info). The session state
  machine is: `CONNECTED → AUTHENTICATING → PLAYING → DISCONNECTING`.
- **Admin REST + WebSocket** — management interface protected by JWT HS256.
  The first WebSocket message must be a `{"type":"auth","token":"<jwt>"}`
  envelope; tokens never appear in URLs.

### Layer 2 — Game Engine

**Tick loop.** Handlers register directly on `TickManager` (no event bus —
`core/events.py`'s EventBus exists but is not wired in). Registered handlers:
`PersistenceManager.on_tick` (flushes Redis → Postgres every 240 ticks ≈ 60 s)
and `EntitySpawnManager.on_tick` (per-tick respawn logic).

**Command pipeline.** Player input flows:
```
raw WebSocket text
  → CommandDispatcher.dispatch(session, raw)
      → tokenize(raw)            shlex split, lowercased
      → registry.get(verb)       primary name or alias lookup
      → handler(session, args)   async, reads/writes Redis
      → [optional] LLMClient.generate(prompt)   fire-and-forget narration
      → session.send(result)
```

**CommandRegistry** is a module-level singleton (`commands/registry.py:70`).
The `@command` decorator registers at import time. Hot reload re-imports
command modules (`registry.reload_module`).

**Proficiency system (Conduit).** Dot-path tree (e.g. `combat.melee.blades`)
gated by five stats (FRT/RFX/ACU/RSV/PRS). `ProficiencyEngine.try_field_gain()`
handles XP math and level caps. `ProficiencyRegistry` is built from the
YAML catalog at startup (or hot-reload). Bonus values feed into
`combat_attack_defense_from_stats()` to produce combat ratings.

**LLM narration.** Every LLM call is wrapped in `try/except`; the handler
falls back to a plain-text message on any failure. The engine never blocks on
LLM output. Prompt templates live in `prompts/*.j2` (Jinja2).

### Layer 3 — State / Data

**Redis** is the hot store. All live game state reads/writes go here.
Key patterns: `player:loc:{id}`, `player:stats:{id}`, `player:inv:{id}`,
`room:players:{id}`, `room:entities:{id}`, `entity:state:{id}`.
`RedisState` (`state/redis_client.py`) provides typed async methods for
every pattern — never hand-craft keys.

**PostgreSQL** is the durable store. SQLAlchemy async ORM models:
`Account`, `Character`, `AdminStaff`, `AccountSceneImage`.
Alembic manages schema migrations (`alembic/versions/`).

**YAML content** is loaded lazily and cached by `ContentLoader`. `HotReloader`
(watchdog) watches `content/` and `commands/` and busts the loader cache on
change, so the next access reloads from disk without a restart.
Room IDs are always `zone_id:room_slug` (file stem).

## Key data flows

### Player command (happy path)

```
WebSocket text  →  WebSocketProtocol  →  CommandDispatcher.dispatch()
  tokenize()                                    shlex, lowercase
  registry.get(verb)                            O(1) dict lookup
  handler(session, args)                        async, may await Redis
  [fire-and-forget] LLMClient.generate()        non-blocking
  session.send(result)                          WebSocket write
```

### Tick cycle

```
TickManager._run_loop()  →  registered tick handlers, in order
  → EntitySpawnManager.on_tick  per-tick respawn rolls
  → PersistenceManager.on_tick  every 240 ticks: flush Redis → Postgres
```

### Content writers

Three independent writers persist `content/world` YAML: the Nexus HTTP API
(`admin/routes/content.py`, the only path with the `expected_mtime` 409
conflict guard), the WorldForge Tauri app (direct disk writes via the Tauri
`write_file` command), and `worldforge-mcp/server.py` (direct disk writes from
the `mcp__worldforge__*` tools). The two direct-disk writers rely on the
HotReloader picking up changes and accept last-write-wins risk — see
CLAUDE.md's "How WorldForge saves (and the conflict risk)".

### Content hot-reload

```
watchdog FileModifiedEvent (content/*.yaml or commands/*.py)
  → HotReloader callback
      → ContentLoader.invalidate(path)     cache bust for that file
      → CommandRegistry.reload_module()    reimport changed command module
```

### Admin action

```
HTTP/WS  →  NexusAdminAuthMiddleware (JWT check)
  →  FastAPI route handler  →  RedisState / PostgresState / ContentLoader
```

## Non-goals

- **No telnet.** Protocol is WebSocket only.
- **LLMs do not decide outcomes.** They produce flavour text after the engine
  has already resolved the action deterministically.
- **No distributed deployment.** Single server process; Redis and Postgres are
  single-node. Horizontal scaling is not a design goal.
- **No in-process LLM inference.** All LLM calls are HTTP to an external
  OpenAI-compatible endpoint (LM Studio / Ollama / OpenAI).
- **No real-money transactions enforced server-side.** `pixels_per_usd` in
  config is a reference rate for storefront math, not enforced by the engine.

## Milestone roadmap

| Milestone | Goal |
|---|---|
| **M1 — Code Quality Foundation** | Green ruff baseline; test coverage for the core pure-logic modules (parser, command registry, config loading, session state machine) that currently have zero tests. |
| **M2+** | TBD — direction decided after M1 lands (gameplay feature, content tooling, or admin improvements). |
