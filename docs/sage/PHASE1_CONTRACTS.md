# SAGE Phase 1 — Contracts

**Status:** **APPROVED 2026-09-13** (v1.0), with the owner amendments folded into the text below
and summarised in Part H. Changes to this contract from here on go through `docs/sage/DECISIONS.md`
first.

**Inputs:** `docs/sage/BRIEF.md` (locked decisions §2, invariants §3) · `docs/sage/PHASE0_AUDIT.md`
(evidence; section references below as "audit §N") · `docs/sage/DECISIONS.md` (owner rulings).

**Owner rulings already made (2026-09-13):**
1. "The standalone map tool" is the WorldForge Tauri app (`worldforge/`).
2. Deliverables live in `docs/sage/`.
3. Agents (computer-controlled players) are a whole plugin; the engine knows nothing about them.

## Contents

- Part A — Target repository shape
- Part B — World package contract
- Part C — Plugin API spec
- Part D — Answers to brief §4 (A–G)
- Part E — Invariant enforcement (brief §3)
- Part F — One-way doors
- Part G — Questions for the owner

---

## Part A — Target repository shape

```
engine/                         SAGE — extractable with `git filter-repo --path engine/`
  pyproject.toml                dist "sage-engine", import package `sage`
  src/sage/                     today's src/fablestar, minus everything world-specific
  alembic/                      core migrations (branch label sage_core)
  lexicon/en.yaml               generic default strings ("You can't go that way.")
  clients/player-ui/            React player client (generic, theme + panels from server)
  clients/admin-ui/             Nexus console
  tools/worldforge/             Tauri world-package editor
  tools/worldforge-mcp/         MCP map tools
  tests/                        engine tests; use worlds/_fixture only
plugins/                        first-party reusable plugins (not tied to one world)
  <id>/plugin.toml
  <id>/sage_plugin_<id>/        python package
  <id>/migrations/              optional alembic branch
  <id>/tests/
worlds/
  fablestar/                    the Fablestar Expanse world package (Part B)
  <world2>/                     the second reference world
  _fixture/                     tiny test world used by engine tests (not shippable)
config/                         per-deployment TOML, gitignored (unchanged)
docs/                           engine + project docs; world docs move into worlds/*/docs
```

Why this shape:
- `engine/` holds its own `pyproject.toml`, migrations, clients and tools, so a paid release is
  a `filter-repo` of one directory (locked decision 4).
- Plugins and worlds are **not** pip-installed. The loader imports them by path under the
  module names `sage_plugins.<id>` and `sage_worlds.<slug>.plugins.<id>`. That keeps the
  one-way import rule checkable (the engine can never have them on its import path by accident)
  and keeps the dev loop to "edit, restart".
- The two React clients and WorldForge are engine assets. Worlds theme them and declare panels
  (C.4 #11); worlds do not ship client code.

---

## Part B — World package contract

A world is a directory of data, templates, assets and world-private plugins. It contains no
engine code and no deployment secrets.

### B.1 Layout

```
worlds/<slug>/
  world.toml                     manifest (B.2) — required
  stats.yaml                     stat schema (B.3) — required
  currencies.yaml                in-world currencies (B.4) — required (may be empty list)
  lexicon/
    <locale>.yaml                player-facing strings (B.5) — required for world.locale
  content/
    zones/<zone>/zone.yaml
    zones/<zone>/.positions.json
    zones/<zone>/rooms/<slug>.yaml
    entities/*.yaml
    items/*.yaml
    <content_type>/*.yaml        one dir per plugin-declared content type (factions/, agents/, ...)
  ai/
    prompts/<slot>.j2            one template per narration/generation slot (B.6)
    style.yaml                   tone, content rules, image style tokens, negative prompt
    comfyui/<role>.json          ComfyUI API graphs (portrait, area, ...)
    loras.yaml                   LoRA references and trigger words, by role
  ui/
    theme.yaml                   client colours, fonts, logo path, title
    assets/                      logo, favicons, backgrounds
  plugins/<id>/                  world-private plugins (same format as Part C)
  docs/                          world lore and design (relocated, not rewritten)
```

### B.2 `world.toml`

```toml
[world]
id          = "fablestar"             # slug; ^[a-z][a-z0-9_]{1,31}$; also the Redis namespace
name        = "Fablestar Expanse"
version     = "1.0.0"                 # semver of the world package
engine      = ">=0.1,<0.2"            # SAGE compatibility range; boot refuses outside it
locale      = "en"

[start]
room        = "test_isle:ferry_landing"
respawn     = "test_isle:clinic"      # read by the default respawn policy

[content]
room_types  = ["chamber", "corridor", "junction", "hub", "safe", "danger", "airlock"]
exit_dirs   = ["north", "south", "east", "west", "up", "down",
               "northeast", "northwest", "southeast", "southwest"]
equipment_slots = ["weapon", "armor"]
day_phases  = [{id = "dawn", minutes = 10}, {id = "day", minutes = 15},
               {id = "dusk", minutes = 5}, {id = "night", minutes = 10}]

[plugins]                             # enabled plugins, load order is resolved, not listed
achievements = "^1"
factions     = "^1"
shop         = "^1"
lodging      = "^1"
agents       = "^1"
conduit      = "^1"                   # world-private: worlds/fablestar/plugins/conduit

[params]                              # world overrides of engine/plugin parameters (audit §5)
"engine.tick_rate"              = 0.25
"engine.respawn.hp_fraction"    = 0.5
"shop.buy_rate"                 = 0.5
"lodging.lease_minutes"         = 80
```

Rules:
- `[params]` keys are declared by the engine or by a plugin, each with a type and default.
  An unknown key, or a key for a plugin that isn't enabled, fails boot.
- `[plugins]` names only enabled plugins. World-private plugins shadow first-party ones with the
  same id (boot logs which one won).
- The world `version` is recorded in Postgres on boot. A downgrade logs a warning; it does not
  refuse to start.

### B.3 `stats.yaml` (locked decision 5)

```yaml
attributes:                          # the world's primary stats; any count
  - key: frt                         # ^[a-z][a-z0-9_]*$ — stored key
    label: stat.frt.name             # lexicon key
    short: stat.frt.short
    min: 8
    max: 23
    default: 13
vitals:                              # pools the engine understands generically
  - key: hp
    label: vital.hp.name
    default_max: 100
chargen:
  attribute_points: 65               # consumed by the default chargen validator
```

- The engine knows only the *shape* (attributes, vitals with current/max, a chargen budget).
  It never names a world's attribute or currency keys.
- `hp` is the one vital the engine itself reads (combat and death). A world that wants a
  different death trigger overrides the `death.check` resolver (C.4 #4).
- Validated on world load, and on every write through the state API (C.5 `api.state`).

### B.4 `currencies.yaml`

```yaml
- key: digi
  label: currency.digi.name          # lexicon: "Digi"
  starting: 100
  integer: true
```

In-world currencies only. The account-level AI-art credit ("pixels") is an **engine** cost
control (locked decision 6). Its display name is a lexicon key (`ai_credit.name`); its prices
are deployment config.

### B.5 Lexicon

```yaml
# lexicon/en.yaml
login.banner: |
  ...
motd: "Welcome to Tidegate Isle."
prompt: "\r\n> "
move.blocked: "You cannot go {direction}."
help.say: "Say something to the room. Usage: say <text>"
currency.digi.name: Digi
stat.frt.name: Fortitude
```

- Keys are dotted; placeholders are `{name}`, filled with a safe formatter (a missing variable
  renders `{name}`, never raises). No plural or ICU engine in v1 (two-world ceiling).
- **Resolution order:** active Nexus override → world `lexicon/<locale>.yaml` → plugin
  `lexicon/en.yaml` → engine `engine/lexicon/en.yaml` → the literal `[key]`.
- The engine and every plugin declare the keys they use. Boot lists required keys the world
  doesn't resolve (a warning in dev, a failure in the CI smoke test).
- **Live edits from Nexus** (locked decision 7) are written as rows in an engine table
  `world_overrides` (B.7). They hot-apply without a restart.

### B.6 AI assets (locked decision 6)

- The engine defines **narration and generation slots**, e.g. `narrate.room`,
  `narrate.combat`, `forge.room`, `forge.content`, `image.area`, `image.portrait`,
  `image.scene`. Plugins may declare more (the agents plugin declares `agent.voice`,
  `agent.intent`, `agent.banter`).
- The world provides `ai/prompts/<slot>.j2` for each slot it wants active. A slot without a
  template is disabled, and the caller uses its deterministic fallback.
- `ai/style.yaml` holds tone text injected into templates as `{{ style.tone }}`, a content
  rules list (replacing the hardcoded regex in `sf/llm/validation.py:16-21`), the default
  system prompt, in-fiction fallback lines (lexicon keys), image style tokens, and the negative
  prompt.
- `ai/comfyui/<role>.json` plus `ai/loras.yaml`: the LoRA stays inside the graph, but
  `loras.yaml` names it per role so Nexus can show and swap it without editing JSON.
- **Versioning with rollback:** the package files are version 0. Nexus edits create
  `world_overrides` rows (kind `prompt`/`style`) with incrementing versions. Rollback activates
  an earlier version. "Export to package" writes the active version back to the files, for the
  operator to commit. Preview/test-run and version diff (brief §10) sit on top of this table
  later.

### B.7 Engine table for live edits

`world_overrides(id, kind, key, version, value jsonb, active bool, author_staff_id,
created_at, note)`, unique on `(kind, key, version)`. Kinds: `lexicon`, `prompt`, `style`,
`param`. There is no `world_id` column — see B.8.

### B.8 One world per deployment, one database per world (owner-approved 2026-09-13)

Locked decision 2 rules out `world_id` columns. The brief also wants switching worlds to be a
config change plus a restart. On a single database, a switch would show world A's characters
and Nexus overrides inside world B. **Proposal:** the database name comes from config and each
world gets its own database (`sage_fablestar`, `sage_<world2>`). Redis is namespaced by world
slug as the brief requires. Switching worlds = change `world` and `database.name`, restart.

### B.9 What a world may and may not contain

| May | May not |
|---|---|
| YAML/JSON/TOML data, Jinja templates, images, fonts | Python outside `plugins/<id>/` |
| World-private plugins (full plugin API) | Imports of engine internals not in the plugin API (C.1) |
| Lore and design docs | Monkeypatching engine modules |
| Parameter overrides (`[params]`) | Secrets, DB URLs, API keys, ports (those stay in `config/`) |
| | Migrations outside a plugin's `migrations/` |
| | Client JavaScript |

---

## Part C — Plugin API spec

### C.1 What a plugin is

```
plugins/<id>/                    (or worlds/<slug>/plugins/<id>/)
  plugin.toml
  sage_plugin_<id>/__init__.py   exposes setup(api) and optionally teardown(api)
  migrations/                    optional alembic version directory
  lexicon/en.yaml                default strings for its keys
  schemas/                       optional JSON Schema overrides for editor forms
  tests/
```

**Import rule.** Plugins import only `sage.api` (the stable surface: `PluginAPI`, event
classes, models, types). Anything under `sage.*` other than `sage.api` is internal. The boundary
is checked by import-linter (Part E).

### C.2 `plugin.toml`

```toml
[plugin]
id          = "shop"                   # ^[a-z][a-z0-9_]{1,31}$
name        = "Shops"
version     = "1.0.0"
engine      = ">=0.1,<0.2"
entry       = "sage_plugin_shop:setup"
first_party = true                     # honoured only for plugins under plugins/ or worlds/*/plugins/

[depends]
factions          = { version = "^1", optional = true }

[touches]                              # the manifest brief decision 3 requires; enforced
commands       = ["browse", "buy", "sell", "wallet"]
events_publish = ["purchase", "sale"]
events_subscribe = []
resolvers      = []
tick_jobs      = ["restock"]
state_blocks   = ["shop_ledger"]
content_types  = []
content_extensions = ["room.shop"]
snapshot       = []
routes         = ["/plugins/shop/*"]
panels         = ["shop.admin.ledgers"]
tables         = []                    # must match ^plg_shop_
redis_prefixes = ["shopstock", "shopledger"]
lexicon_prefix = "shop."
params         = ["shop.buy_rate", "shop.resale_rate", "shop.stock_cap"]
ai_slots       = []
```

### C.3 Lifecycle

1. **Discover.** Read `world.toml [plugins]` and locate each id in `worlds/<slug>/plugins/`,
   then `plugins/`.
2. **Validate manifests.** Schema, id format, the `engine` range against the running SAGE
   version, and dependency version ranges. Any failure stops boot with the plugin named.
3. **Resolve order.** Topological sort on `depends`. A cycle or a missing required dependency
   fails boot. Ties break by id, so the order is deterministic.
4. **Trust banner.** Any plugin whose path is outside `plugins/` and `worlds/*/plugins/`, or
   without `first_party = true`, logs a multi-line WARNING naming its path and its `touches`
   (locked decision 3). No sandbox.
5. **Migrations gate.** If any enabled plugin (or core) has unapplied migrations, boot refuses
   with the exact `sage db upgrade` command to run. No auto-migrate on boot (D.4).
6. **Setup.** Call `setup(api)` in resolved order. The `api` object is scoped to the plugin:
   everything it registers is tagged with the plugin id.
7. **Seal.** Compare actual registrations with `[touches]`. **Anything registered but not
   declared fails boot.** Declared but unregistered gets a warning.
8. **Start.** The engine starts the tick loop and the network.
9. **Shutdown.** `teardown(api)` in reverse order, then the engine flushes persistence.

**Uninstall** (`sage plugin uninstall <id> [--purge-state]`):
1. Refuse if an enabled plugin depends on it.
2. Downgrade its alembic branch to base (drops its tables).
3. With `--purge-state`, remove its state blocks from every character row and its Redis prefixes.
4. Remove it from `world.toml`.

Without `--purge-state`, the state blocks stay dormant so a reinstall recovers them.

### C.4 Extension point catalog (the engine's public plugin API)

Finite. Anything not listed is core engine and not pluggable (brief §4A). Full reasoning is in
D.A.

| # | Extension point | Registration | Shape |
|---|---|---|---|
| 1 | Commands | `api.commands.register(verb, handler, aliases, help_key, permission)` | multi, unique verbs; conflict fails boot |
| 2 | State blocks | `api.state.block(name, Model, default, upgrade)` | namespaced key in the character state JSONB; validated on load and write |
| 3 | Progression provider | `api.resolvers.provide("progression", impl)` | single; gives level/xp display, `on_skill_use`, chargen seed |
| 4 | Resolver slots | `api.resolvers.provide(slot, fn)`. Engine slots: `death.check`, `death.respawn`, `chargen.validate`, `chargen.seed`. Plugins may define their own with `api.resolvers.define(slot, default)` — e.g. the combat plugin defines `combat.resolve`, which Fablestar's `conduit` provides | single provider per slot; the defining owner's default if none; two providers fail boot |
| 5 | Domain events | `api.events.subscribe(EventType, handler)`, `api.events.publish(event)` | fan-out, no return value |
| 6 | Tick jobs | `api.tick.every(seconds, fn, name)` | multi; errors logged per job |
| 7 | Content types and schema extensions | `api.content.type(name, dir, Model)`, `api.content.extend("room"\|"item"\|"entity", field, Model)` | new YAML dirs, and extra fields on engine content models |
| 8 | Snapshot contributors | `api.snapshot.contribute(section, fn)` | ordered multi; adds a section to the client character snapshot |
| 9 | HTTP routes | `api.http.play_router(router)`, `api.http.admin_router(router, tool)` | mounted under `/plugins/<id>/`; admin routes behind a tool permission |
| 10 | AI slots | `api.ai.slot(name, fallback_key)` | declares a template slot the world can fill (B.6) |
| 11 | Declarative UI panels | `api.ui.panel(id, surface="player"\|"admin", kind, source)` | kinds: `stat_sheet`, `wallet`, `tree`, `list`, `key_value`, `schema_form`, `table`; the data source is a snapshot section or a plugin route. `kind = "module"` (plugin-shipped client code) is **reserved**: the schema accepts it, boot rejects it as unsupported in this engine version |
| 12 | Migrations | `migrations/` dir + `[touches].tables` | alembic branch per plugin (D.D) |
| 13 | Plugin services | `api.services.provide(name, obj)`; dependents call `api.services.get(name)` | lets a mechanic plugin (effects, equipment, combat) offer an API to plugins that declare it in `[depends]`; getting an undeclared service fails boot |

### C.5 Engine services plugins may call

The other half of the public surface. Plugins call these; they don't register them.

| Service | Purpose |
|---|---|
| `api.world` | manifest, stat schema, currencies, `params.get(key)` |
| `api.lexicon` | `t(key, **vars)`; `session.say(key, **vars)` sends a resolved string |
| `api.state` | typed get/update of a character's blocks (per-block Redis keys, D.D) |
| `api.wallet` | `balance`, `credit`, `debit` (atomic, refuses overdraft), per declared currency |
| `api.rooms`, `api.entities`, `api.items` | content lookups, room occupants, spawn/despawn |
| `api.sessions` | broadcast, find by player, **virtual sessions** (socketless players with a `kind`, for the agents plugin) |
| `api.dispatch` | run a command as a session (agents, maestro) |
| `api.ai` | `narrate(slot, ctx)`, `generate(slot, ctx)`, `image(role, ctx)`; all go through engine routing, breaker, budgets and the AI-credit ledger |
| `api.clock` | day phase, game time |
| `api.redis` | a client pre-scoped to `<world>:plg:<id>:` — raw keys outside the declared prefixes are impossible |
| `api.log` | a logger named `sage.plugin.<id>` |

### C.6 Load-order and dependency rules

- Dependencies are on plugin ids with semver ranges, optionally `optional = true`. An optional
  dependency that is absent is skipped; one that is present participates in ordering.
- A plugin may subscribe to events published by a plugin it doesn't depend on. Unknown event
  types are a boot failure only if no enabled plugin or the engine declares them.
- Two plugins registering the same command verb, resolver slot, state block, content type,
  route prefix, Redis prefix or lexicon prefix fail boot — except world-private plugins, which
  may override a first-party resolver *if they declare it* in `[touches].resolvers`.
- The engine registers its own defaults under the pseudo-plugin id `sage`.

---

## Part D — Answers to brief §4

### D.A Extension point catalog

Starting list → decision, with the audit evidence:

| Brief's proposal | Decision | Why |
|---|---|---|
| command verbs | **Keep** (#1) | The registry exists and works (`sf/commands/registry.py`). It gains owner, help key, permission and unregister (unregister landed in Phase −1, `6e27147`). |
| entity components | **Replace with state blocks** (#2) | There is no component system to extend. What exists is an unnamespaced stats blob where each subsystem owns top-level keys by convention (audit §8). Formalising that as named, typed blocks gives worlds real per-mechanic data without inventing an ECS. |
| stat and progression systems | **Keep, split** (stat schema = world data B.3; progression = resolver #3) | The stat *shape* is generic; FRT..PRS is data. Progression differs structurally between the two worlds (a 278-leaf tree vs levels), so it has to be code. |
| abilities | **Cut** | No ability runtime exists. Glyphs are mock UI panels and a dead `GlyphModel` (audit §6, §11.7). With two worlds as the ceiling (brief §8), commands + state blocks + effects cover ability-like mechanics. If Fablestar's design needs glyphs, they are built as a plugin using those three. Brief decision 1's "glyphs become a plugin" is satisfied without a dedicated point. |
| combat resolution | **Combat is a first-party plugin that defines the `combat.resolve` slot** (#4, amended per owner G.4) | A world without combat simply doesn't enable it. Within combat, only the math is world-specific (`sf/proficiencies/state_helpers.py:75-107`), and it returns a value, so the plugin exposes it as a resolver that world plugins like `conduit` replace. |
| economy and currency | **Cut as an extension point; becomes an engine service** (`api.wallet`) + data (B.4) | Currencies are data. The wallet is generic (balance, atomic debit/credit). What's world-specific is shops and rent, and those are plugins built on the wallet. |
| room and content generation | **Fold into #7 content types + #10 AI slots** | Generation today is LLM forge endpoints producing YAML. That is an AI slot writing a content type, not a separate mechanism. |
| AI narrative hooks | **Keep as AI slots** (#10) | Narration call sites are already slot-shaped (`narrate room`, `narrate combat`); the template, tone and fallback move to the world. |
| scheduled tick jobs | **Keep** (#6) | `TickManager.register` exists; it gains owner name, interval and per-job error logging (logging landed in `3d4cf48`). |
| event bus subscriptions | **Keep, and make the bus real** (#5) | `core/events.py` has zero users (audit §6). Combat currently calls achievements, factions and missions inline (`sf/commands/combat.py:177-228`) — exactly the coupling a bus removes. |
| client UI panels | **Keep, declarative only** (#11) | Both clients hardcode Fablestar panels. Plugin-shipped React would need a plugin build pipeline and a client module loader — real cost for two worlds. Seven generic panel kinds cover every existing panel (Conduit sheet = `stat_sheet` + `tree`; wallet chip = `wallet`; factions = `list`; skills = `tree`). |
| Nexus admin panels | **Merge into #11** (surface `admin`) + #9 admin routes | Same mechanism as player panels. Schema-driven forms come from the plugin's pydantic models. |
| — | **Add: snapshot contributors** (#8) | The client snapshot is how the UI learns state. Today it hardcodes `resonance_levels_total` (`sf/network/play_messages.py`). Without this point the protocol stays Fablestar-shaped. |
| — | **Add: HTTP routes** (#9) | Proficiency catalog, shops and agents already have REST routes. Plugins need to bring theirs. |
| — | **Add: content schema extensions** (#7) | `RoomModel` carries shop, lodging, hazards, ambient and search fields today (audit §11.8). Plugins must add YAML fields without editing engine models. |
| — | **Add: migrations** (#12) | Locked decision 8. |

### D.B Hook mechanism — both, split by shape

- **Event bus** for notifications: fan-out, no return value, order-independent. Examples:
  `EntityKilled`, `PlayerDied`, `RoomEntered`, `ItemUsed`, `Purchase`, `CommandExecuted`,
  `CharacterCreated`, `SessionStarted`, `SessionEnded`.
- **Typed resolver registry** for decisions that return a value and must have exactly one
  answer: `combat.resolve`, `death.check`, `death.respawn`, `chargen.validate`,
  `chargen.seed`, `progression`. Ordered **contributors** (snapshot sections) use the same
  registry with a multi shape.

Why not only a bus: combat needs a result back, and "first subscriber wins" on a bus is an
invisible ordering bug. Why not only hooks: achievements, factions and missions all react to a
kill independently; a hook chain would make each a dependency of combat.

Bus changes needed (small):
- Log handler exceptions with the handler and plugin name. Today async failures are dropped
  (`core/events.py:63-64`) and sync ones propagate into the publisher.
- Publish to subscribers in plugin load order, awaiting handlers (current behaviour, kept).
- Event classes live in `sage.api.events`. Plugins can define their own event classes if they
  declare them in `[touches].events_publish`.

### D.C Plugin reload — restart by default, one exception

- **Plugin Python code:** restart on change. Reloading tick jobs, subscribers, resolvers,
  state models and routes in place is where hot-reload bugs live, and a Nexus restart is a few
  seconds.
- **Exception (dev mode only):** modules containing *only* command handlers keep hot reload.
  It already works, handlers are stateless, and it is the tightest part of the dev loop. The
  Phase −1 unregister fix makes it correct.
- **Data keeps hot reload:** content YAML, lexicon, prompts, style, and Nexus overrides.
- **Manifest changes** (`world.toml`, `plugin.toml`) need a restart.

### D.D Migrations and schema

**Alembic layout.**
- The existing 11-revision chain becomes core history. A new core revision adds the branch label
  `sage_core`.
- Each plugin with tables ships `migrations/`. Its first revision has `down_revision = None`,
  `branch_labels = ("plg_<id>",)` and `depends_on = "<core revision it needs>"`.
- `alembic/env.py` builds `version_locations` from core plus enabled plugins.
- Commands: `sage db upgrade` runs `upgrade heads`. `sage plugin uninstall` runs
  `downgrade plg_<id>@base`.
- Plugin tables must be named `plg_<id>_*`; boot checks ownership against `[touches].tables`.
- Interleaving: a plugin revision may depend on a core revision, never on another plugin's
  revision unless it declares that plugin in `[depends]`. Core never depends on a plugin.

**Character state (locked decision 5).**
- `characters.stats` JSON → `characters.state` **JSONB**, with a top-level map of blocks:
  `{"core": {...}, "vitals": {...}, "attributes": {...}, "wallet": {...}, "conduit": {...}, ...}`.
  Each block carries its own `_v` schema version, and the block's `upgrade` fn migrates old
  shapes lazily on load.
- **Redis:** per-block keys `<world>:player:<id>:state:<block>` instead of one blob. This
  removes today's read-modify-write races between subsystems that each rewrite the whole stats
  blob (`sf/state/redis_client.py:115-126`), and validation becomes per block.
- No generated columns or indexes for now. Nothing queries stats across players in SQL today
  (the stat board computes in Python). Add one only when a real cross-player query appears.

**Fablestar columns** — each one a sequence of separate, playable commits (backfill, switch
reads, drop):

| Column | Target | Door |
|---|---|---|
| `characters.digi_balance` | `state.wallet.digi` | one-way (drop) |
| `characters.reputation` | state block of a Fablestar `morality` plugin (only the thermometer uses it) | one-way (drop) |
| `characters.room_id` default `test_isle:ferry_landing` | no DB default; engine writes `world.start.room` | reversible |
| `characters.stats` JSON | `characters.state` JSONB (rename + type change) | one-way |
| `accounts.echo_credits` | `accounts.ai_credits` (engine AI cost ledger) | rename; reversible with a view |
| `agent_state` table | adopted by the agents plugin as `plg_agents_state` (core revision renames; the plugin's base revision creates it if absent) | one-way |

**Redis namespace (locked decision 2).** Every key gets the `<world_slug>:` prefix. All
key construction moves into `RedisState` and `api.redis`. That fixes
`get_all_active_player_ids` splitting on `:` (`sf/state/redis_client.py:78-79`) and the ~6
raw-key sites (audit §8). Redis is hot state, so the cutover is "flush Redis on the restart that
ships it". Persistence has already written everything durable to Postgres; no data migration.

### D.E Tool surface — decided as a set

| Tool | Decision | Route |
|---|---|---|
| **WorldForge** (Tauri) — "the map tool" (owner ruling) | **Becomes the SAGE world-package editor**, ships with the engine (`engine/tools/worldforge`) | Opens a world package by `world.toml`. Content forms are generated from JSON Schema exported by the engine and enabled plugins (`sage schema export`, also `GET /schema/world`); room types, exit directions and equipment slots come from `world.toml`. Its zone graph editor, floors, stamps and ELK layout are the map/graph layer. It adds an optional **Nexus write-through backend** (the existing `/content/*` routes with `expected_mtime`) for editing a remote server. The map tool therefore doesn't need to fold into WorldForge — it *is* WorldForge, and the brief's "WorldForge spec" should be designed as this app's roadmap rather than a new build (owner question G.1). |
| **admin-ui World Builder** | **Folds into WorldForge; deprecated** | A duplicate xyflow editor with a byte-identical `AutoLayout.js`, fewer directions, no floors, and the source of the floors data loss (fixed in `2a80ab9`). Removing it drops the room writers from three to two. Remote staff edit through WorldForge's Nexus write-through backend. |
| **Nexus admin console** (rest of admin-ui) | **Stays; engine-owned, world-agnostic** | Live ops, sessions, staff, accounts, content library (read + schema forms), lexicon/MOTD/prompt/style editing with versions and rollback, plugin admin panels (C.4 #11). Hardcoded USD bundles move to deployment config. |
| **worldforge-mcp** | **Stays standalone, world-agnostic** | Reads the package format and gets room types from `world.toml`; its layout instructions lose the sci-fi examples. `validate_zone` logic moves into one engine Python module (`sage.world.validate`) shared by the MCP server, a `sage validate` CLI and Nexus. WorldForge's JS validation stays until it can call Nexus or the CLI. |
| **Galaxy / System / Ship / Glyph editors and models** (in both WorldForge and admin-ui; `StarSystemModel`, `ShipTemplate`, `GlyphModel`; client mock panels) | **Deprecated → deleted** | No content and no runtime (audit §11.7); brief §8 "prefer deleting". **Pending the vault check** (G.3): if Fablestar's design needs them, they return as Fablestar plugin content types edited through schema forms. |
| **player-ui** | **Engine client, world-themed** | Theme, title and logo from `ui/theme.yaml`; panels from C.4 #11; labels from lexicon; no Fablestar fallbacks. |
| WorldWeaver, terrain-forge, Feyndral City Map Maker (sibling repos) | **Out of scope** | Unrelated to Fablestar content. |

### D.F Things the brief missed

Raised in audit §11, repeated here as design inputs:
1. The **wire protocol** is its own decoupling surface → snapshot contributors (#8).
2. **Client-duplicated mechanics** → declarative panels (#11) plus a server-sent command list
   for autocomplete.
3. **Two kinds of currency** → wallet (world) vs AI-credit ledger (engine); USD bundles are
   deployment config.
4. **Cwd-relative paths** → one `sage.paths` resolver built from `config.world` + `worlds_dir`.
5. **Tests reading live content** → `worlds/_fixture` for engine tests; world packages keep
   their own content tests.
6. **No CI** → Phase 2a.
7. **Dead world code** → delete (pending the vault).
8. **Engine content models carrying plugin fields** → content schema extensions (#7).
9. **Agent filtering in admin** → virtual sessions have a `kind`; admin lists filter by kind,
   not `is_agent`.
10. **Global interpreter** → a clean venv in CI, used for the license audit.
11. **Client theming** → `ui/theme.yaml` (fonts and colours are world branding).
12. **Epitaph-derived systems** (ambient, search, effects, hazards, factions) → classification
    below (G.4).

### D.G The plan itself — proposed changes to brief §5

1. **Phase −1 replaced** by the audit-found breakages. Done (audit §2).
2. **Split Phase 2 into three stages, in this order:**
   - **2a — CI and ratchets.** GitHub Actions with Redis and Postgres service containers:
     format, lint, compile, pytest, WorldForge vitest, a clean-venv license report, and the
     invariant checks from Part E in *ratchet* mode. Full compliance is impossible until Phase 3
     ends, so each check stores a baseline and fails if anything gets worse. This is the
     mechanical alternative the brief asked for.
   - **2b — Mechanical move and rename.** `src/fablestar` → `engine/src/sage`,
     `FablestarServer` → `SageServer`, clients and tools into `engine/`, gates in
     `rexymcp.toml` and `REXYMCP.md` updated. One big but purely mechanical commit per
     directory, suite green after each. `FABLESTAR_*` env vars stay accepted as aliases for one
     release.
   - **2c — Seams and loader.** `sage.api`, plugin loader, lexicon service, world loader,
     resolver registry, a real bus, state blocks, paths resolver, `world_overrides`. Fablestar
     keeps running because each seam ships with a default that calls today's code
     (strangler pattern).
3. **Build a skeleton second world in 2c, not Phase 4.** Three rooms, three attributes, one
   currency, a `levels` progression plugin, no agents. It boots in CI from the first day the
   loader exists, so every seam cut in Phase 3 is exercised by two worlds as it lands. That
   targets the brief §6 failure mode directly: abstractions never get a chance to set around
   Fablestar alone. The full 20–40 room world stays in Phase 4.
4. **Phase 3 order** — lowest coupling first, so the game stays playable and each step
   proves the API before the hard ones:
   1. lexicon (strings only)
   2. paths and world manifest
   3. achievements
   4. factions + missions (bus)
   5. shop and lodging (wallet)
   6. crafting and search
   7. maestro
   8. hazards
   9. agents plugin
   10. Conduit into `worlds/fablestar/plugins/conduit` (resolvers + state block + panels)
   11. death/respawn policy
   12. protocol snapshot contributors
   13. client panels
   14. schema migrations (backfill → switch reads → drop)
   15. Redis namespace
   16. AI slots and style
5. **Tooling decisions now, tooling work split.** Deprecating the admin World Builder can
   happen as soon as WorldForge covers its fields (it already does, apart from shop/lodging/
   ambient/search, which none of the three tools edit). Schema-driven forms wait for 2c.

### Classification (approved; amended per owner G.4)

| Where | Systems |
|---|---|
| **Engine** (runtime infrastructure only) | network, sessions (incl. virtual sessions), parser, command registry, tick, bus, resolvers, plugin services, Redis/Postgres state, persistence, content loader (rooms/entities/items + extensions), spawner, clock (phases from world), wallet, death check + respawn policy defaults, lexicon, world loader, plugin loader, AI (LLM client, breaker, embedded, ComfyUI client, AI-credit ledger, slots, overrides), Nexus core, clients, tools. **Universal verbs only:** look, move, say/emote/tell, who, help, inventory/take/drop/examine, quit |
| **First-party plugins** (`plugins/`) | `combat` (attack/flee, loot, kill events, defines `combat.resolve`), `effects` (timed DoT/HoT/flags, rest; exports the effects service), `equipment` (slots from world, equip/unequip, item attack/defense fields), `ambient`, `hazards` (depends on effects), `search`, `crafting`, `achievements`, `factions` (+ missions), `shop`, `lodging`, `maestro`, `agents` (owner ruling; also takes over the lease sweep now in `sf/agents/manager.py:289-295`) |
| **Fablestar world plugins** | `conduit` (proficiency tree, FRT..PRS combat resolver, resonance cap, chargen allocation, skill panels), `morality` (reputation thermometer) |
| **World 2 plugins** | `levels` |
| **Deleted** (owner G.3) | glyph/ship/system/galaxy models and editors, mock client panels, admin-ui World Builder (owner G.6) |

---

## Part E — Invariant enforcement (brief §3)

| # | Invariant | Mechanical check | Fully mechanical? |
|---|---|---|---|
| 1 | `engine/` never imports `worlds/` or `plugins/` | `import-linter` contract: `sage` forbidden from `sage_plugins`, `sage_worlds`. Plus an AST check that bans `sys.path` manipulation and `importlib` with plugin/world paths outside `sage/plugins/loader.py`. Plugins are limited to `sage.api` by a second contract. | **Yes** |
| 2 | No world-specific literals in `engine/` | A denylist scanner over `engine/` (Python via AST string constants and comments; JS/JSX/TS and YAML/JSON via token scan). Denylist = the brief's seed list + FRT/RFX/ACU/RSV/PRS, Tidegate, AIpub, `test_isle`, Digi, pixels, echo_credits + **every stat key, currency key, zone id and lexicon label value auto-extracted from both reference worlds**. "Resolve", "Presence" and "Reflex" are matched case-sensitive as whole words in string literals only, so identifiers like `resolve_project_root` and JS `Promise.resolve` don't trip it. Ratchet baseline until Phase 3 ends, then zero. | **Yes**, with a small reviewed allowlist file for real false positives |
| 3 | Every player-facing string is a lexicon key | AST lint: in `engine/` and `plugins/`, `session.send(...)`, `broadcast(...)` and friends may not receive a string literal, f-string or `%`/`.format` expression. Player text must go through `session.say(key, **vars)` / `api.lexicon.t`. JSON protocol frames use `session.send_json`. The React clients get an ESLint rule banning JSX text literals outside a `t()` call in `engine/clients`. | **Mostly.** Strings built indirectly (a variable holding a literal) escape the lint; code review covers the remainder. The CI smoke test also fails on any rendered `[missing.key]`. |
| 4 | Engine has no knowledge of stat, currency or ability names | Covered by #2's auto-extracted world keys (both worlds, so the engine can't name *either* world's stats), plus a test that boots the engine with `worlds/_fixture`, whose stat and currency keys are random per run. | **Yes** |
| 5 | Both reference worlds boot and pass smoke tests in CI | CI job per world: `sage db upgrade`, boot, dev login, scripted session (look, move, say, plus attack/die/respawn and buy when those plugins are enabled, quit), assert no ERROR logs and no `[missing.key]`, plugin uninstall/reinstall round-trip on a throwaway DB. | **Yes** |

---

## Part F — One-way doors

Each gets its own announced commit, never bundled with other changes.

1. **Package and class rename** `fablestar` → `sage` (imports, env prefix, console script,
   localStorage keys, Tauri identifier — a new Tauri identifier resets WorldForge's saved root
   and settings on users' machines). Mitigation: env aliases for one release; a one-time
   localStorage migration in each client.
2. **Dropping `characters.digi_balance` and `characters.reputation`** after backfill.
3. **`stats` JSON → `state` JSONB** with block namespacing.
4. **`agent_state` → `plg_agents_state`.**
5. **Redis key namespace** — needs a Redis flush on that restart. Durable state is safe;
   in-flight shop stock and leases in Redis-only keys (`shopstock:*`, `rentals`) are lost unless
   first copied, so that commit copies them.
6. **Deleting the galaxy/system/ship/glyph surfaces** — reversible through git, but only after
   the vault check.
7. **Database per world** — creates a second database; the Fablestar DB is renamed or kept by
   config.

---

## Part H — Owner amendments at approval (2026-09-13)

| Question | Answer | Effect on this contract |
|---|---|---|
| G.1 WorldForge spec | None yet | WorldForge roadmap = D.E |
| G.2 Database per world | Yes | B.8 approved |
| G.3 Glyph/ship/system/galaxy | Not needed at this time | Deleted when Phase 3/5 reaches them |
| G.4 Engine vs plugin split | Delegated: "more modular and editable for a user" | Every mechanic is a plugin, incl. ambient, effects, combat, equipment; catalog #13 plugin services; plugins may define resolver slots |
| G.5 Rename | Yes — "SAGE - Synthetic Agent Game Engine" | F.1 approved |
| G.6 Admin World Builder | Retire | D.E approved |
| G.7 Test tiers | Delegated | Hermetic unit tier by default + required live Postgres/Redis tier for migrations, persistence, plugin install/uninstall, world smoke; migrations and persistence never tested only against fakes |
| G.8 License | FSL-1.1-ALv2 engine, Fablestar proprietary | `engine/LICENSE`, `NOTICE` |
| G.9 Second world | No set genre; SAGE builds any world. Architect picks the harness | Low-fantasy river town, Might/Wits/Nerve, silver, `levels`, no agents, no AI images |
| G.10 Plugin client code | Delegated: best long-term | Declarative panels in v1; `kind = "module"` reserved and rejected at boot |

## Part G — Questions for the owner (all answered, see Part H)

**Answered 2026-09-13** (details in `docs/sage/DECISIONS.md`): **2** yes, one database per world ·
**3** not needed at this time, delete when reached · **5** rename approved, official name
"SAGE - Synthetic Agent Game Engine" · **8** engine under `FSL-1.1-ALv2`, Fablestar content
proprietary (`engine/LICENSE`, `NOTICE`). **Still open:** 1, 4, 6, 7, 9, 10.

1. **WorldForge spec.** The brief says WorldForge is specced but unbuilt; the repo's WorldForge
   is built and you've ruled it's the map tool. Is there a separate WorldForge spec (vault or
   Cursor prompt) whose features should become this app's roadmap?
2. ~~**One database per world (B.8)?**~~ **Answered: yes.** It's the only way to honour "no `world_id` columns" and
   "switch worlds with config + restart" together.
3. ~~**Glyphs, ships, star systems, galaxy.**~~ **Answered: not needed at this time; delete.** No content or runtime exists. Delete now, or does
   the vault's Fablestar design need them (then: Fablestar plugin content types)?
4. **Epitaph systems.** Proposal: ambient and effects stay engine (genre-neutral, used by both
   worlds); search, hazards, factions/missions, crafting, maestro become first-party plugins.
   Agree?
5. ~~**Package rename and compatibility window (F.1).**~~ **Answered: approved; name "SAGE - Synthetic Agent Game Engine".** OK to rename to `sage` in Phase 2b, with
   `FABLESTAR_*` env aliases for one release?
6. **Deprecate the admin-ui World Builder (D.E)?** Remote builders would then need the
   WorldForge desktop app pointed at Nexus.
7. **Tests:** does "don't mock the database" still hold? The current suite is hermetic. Proposal:
   hermetic unit tests stay; Phase 2a adds a live Postgres/Redis job for migrations, plugin
   uninstall and the world smoke tests.
8. ~~**License.**~~ **Answered: FSL-1.1-ALv2 for the engine; Fablestar proprietary.** `pyproject.toml` declares MIT and there is no LICENSE file. With a paid release
   in mind, should the engine be marked proprietary until you decide? (elkjs EPL-2.0 is fine
   unmodified.)
9. **Second world.** Proposal for the skeleton: low-fantasy river town, attributes Might / Wits /
   Nerve, currency silver, `levels` progression, no agents, no AI images. Or modern day?
10. **Declarative panels only (no plugin-shipped client JS) for v1?**
