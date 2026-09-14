# Zero to first world: onboarding plan

Status: **approved by the owner 2026-09-14.** Stage 1 items 1 (JWT secret refusal) and 2 (demo
world) are implemented; the rest is not yet.

Revised 2026-09-14 after owner feedback: *starting a world should not include building the map,
which is the tools' job (the map builder); get the player set up with the engine first, world
building second; the engine can come with a default four-room start as a demo.* Onboarding is
therefore two stages: **(1) the engine running a bundled demo world**, then **(2) building your
own world with the tools.**

SAGE's seams hold: `sage.api` is the only import surface for plugins, `[touches]` seals what a
plugin may do, and Rivermoot runs a different world on the same engine code. What is missing is
the road from a stranger's `git clone` to a running engine, and from there to a world of their
own. This plan measures that road as it is today, sets a target for each stage, and designs the
commands, the demo world and the tutorial that get there.

---

## 1. Target experience

### Stage 1: the engine running, playing the demo

**Success:** a newcomer goes from `git clone` to walking around the bundled four-room demo world,
and changes something they can see, in **under 10 minutes of wall-clock time, with 5 commands,
one terminal, and no file edited by hand.**

Prerequisites: Python 3.11+, Node.js LTS, Docker, and Git are already installed. Installing them is
outside this budget, as it is for every engine's getting-started page.

```bash
git clone https://github.com/Fablestarexpanse/sage-engine && cd sage-engine   # 1
python -m venv .venv && . .venv/bin/activate                                   # 2  (Windows: .venv\Scripts\activate)
pip install -e ./engine                                                        # 3
sage quickstart                                                                # 4  services, config, database, client build, server, demo world
# 5: open http://localhost:8001, press "Play", walk the four demo rooms.
```

Then edit one demo room's description and type `look` to see it change without a restart. Stage 1
ends there: the newcomer has a working engine and has seen that a world is data the engine reads.

### Stage 2: building a world with the tools

**Success:** from a running Stage 1 setup, a newcomer creates a new world, draws at least three
connected rooms in WorldForge's map builder, and walks them, in **under 20 minutes, with no
hand-written room YAML and no hand-edited config.** Creating the world makes the package; drawing
the map is done in the editor, not by a scaffold.

Why these numbers:
- **10 minutes for Stage 1.** The unavoidable machine time is short. Measured in section 2, the
  engine install takes 49–54 s, the client installs 3–10 s, and the services, migrations and first
  boot under 10 s. Cold Docker image pulls add about a minute, which was not measured because the
  images were cached. That leaves several minutes for reading and for a slow first `pip install`.
  Stage 1 no longer includes making a world, so it can be shorter than the first draft's 15.
- **5 commands.** Today's path is 18 (section 2). Commands 1–3 are standard for any Python project
  and cannot be removed without a packaged release; `quickstart` is the one new command, and
  opening the browser is the fifth. Every other step belongs inside `quickstart`, because each one
  is a place a newcomer can go wrong.
- **One terminal and zero hand edits.** Today it is 3 terminals and 5 edits, one of which is
  undocumented and fails silently (section 2). Configuration a newcomer does not understand yet
  must be generated, not typed.
- **20 minutes for Stage 2.** Most of it is the newcomer designing and describing rooms, which is
  the point. The measured copy-a-world path (section 2) took 5 commands and 3 hand edits before
  anything was drawn, and left 15 mentions of the copied world behind.

## 2. The current path, measured

Measured 2026-09-14 on Windows 11 (Git Bash). It started from a fresh `git clone` of
`Fablestarexpanse/sage-engine` at `f1dd9b5` (main) into an empty directory, with a new virtual
environment, following only `README.md`.

**Deviations from a truly clean machine.** Each one makes today's path look better, not worse:
- Python, Node, Docker and Git were already installed. The `postgres:16-alpine` and
  `redis:7-alpine` images were already pulled.
- The developer's own Postgres and Redis containers held ports 5432 and 6379, so the clean run
  used 55432 and 56379 (through a compose override and one extra `database.toml` edit that a real
  newcomer would not need), and Nexus on 18001 to stay clear of the developer's usual 8001.
- The README never says to use a virtual environment; one was used anyway.
- Player actions went through the same HTTP and WebSocket routes the player client uses,
  scripted, because passwords are not typed into browser forms in this session. Client dev
  servers were not started in the clean clone; their install time is measured.

| # | Step (as the README says) | Machine time | Notes |
|---|---|---|---|
| 1 | `git clone` | 2 s | |
| 2 | `cd sage-engine` | — | |
| — | `python -m venv` (not in README) | 12 s | Decision with no guidance: global install or venv. |
| 3 | `pip install -e "./engine[dev]"` | 49 s warm cache, 54 s cold (`--no-cache-dir`, includes venv) | The README installs `[dev]` extras, which a player does not need. |
| 4 | `npm install` in `player-ui` | 10 s warm, 3 s cold cache | |
| 5 | `npm install` in `admin-ui` | 3 s | |
| 6 | `cp config/server.example.toml config/server.toml` | — | |
| 7 | `cp config/database.example.toml config/database.toml` | — | |
| 8 | `echo "POSTGRES_PASSWORD=…" > .env` | — | Decision: choose a password. |
| E1 | Hand edit: the same password in `config/database.toml` | — | The README says so; it is easy to miss. |
| 9 | `docker compose up -d redis postgres` | 1 s | |
| 10 | `python -m sage db upgrade` | 2 s | Upgraded core and 16 plugin branches, **for Fablestar**. |
| 11 | `python -m sage` (terminal 1) | healthy after 4 s | Boots **Fablestar Expanse**, the proprietary world, because `server.example.toml` says `world = "fablestar"`. |
| — | Register and create a character | — | **Fails: HTTP 500.** The server log says `admin_auth_required is true but no JWT secret is configured`. The README quick start never mentions the secret, and the server reports healthy anyway. |
| E2 | Hand edit: set `admin_jwt_secret` in `config/server.toml`, then restart | — | Found only by reading the server log. After this, register, create, `look`, `say`, `north` and `quit` all worked, in 0.5 s. |
| 12 | Player client dev server (terminal 2) | not timed | Needs `VITE_NEXUS_PORT` set in the environment, spelled differently on PowerShell. |
| 13 | Admin client dev server (terminal 3) | not timed | Signing in needs a staff account the quick start never creates: `engine/scripts/bootstrap_admin.py` with another password, from the Configuration section. |

Making **your own world**. None of this is in the README:

| # | Step | Result |
|---|---|---|
| 14 | `cp -r worlds/rivermoot worlds/mytown` | `sage validate --world mytown` fails: `world id 'rivermoot' must match its directory name 'mytown'`. |
| E3 | Hand edit `world.toml`: `id`, `name` | Validate passes: 30 rooms, 0 errors, 0 warnings. |
| 15 | Create the world's database: `docker compose exec postgres createdb -U fablestar sage_mytown` | The README says "create the database in PostgreSQL first" and gives no command. |
| E4 | Hand edit `server.toml`: `world = "mytown"` | |
| E5 | Hand edit `database.toml`: `database = "sage_mytown"` | Alternatively the two `SAGE_…` environment variables the README shows. |
| 16 | `python -m sage db upgrade` | Upgraded core and 10 plugin branches. |
| 17 | Restart the server | `/play/world` reports `My Town`. |
| 18 | Edit a room description, `look` | Hot reload worked in about 3 s. But the login banner still says **"~ Rivermoot ~"**: 15 mentions of Rivermoot remain in 10 files (`world.toml` comments, lexicon, theme, zone name, one room, two AI prompts, style, the `levels` plugin manifest, the exported schema). The copy also carries Rivermoot's `LICENSE`. |

**Baseline totals**
- **Commands:** 18, including three undocumented ones: venv, createdb, restart.
- **Hand-edited files:** 5 edits across 3 files (`database.toml` ×2, `server.toml` ×2, `world.toml`), plus 10 files carrying the old world's name.
- **Terminals:** 3.
- **Failures a newcomer hits:** 2. Registration returns 500 without a JWT secret, and validate fails after copying a world.
- **Decisions with no guidance:** 8. Venv or not; the database password; the JWT secret, which is silent until it breaks; which world to run (the default is the proprietary one); ports; the database name for a new world; how to create that database; which files still name the copied world.
- **Machine time:** about 83 s with warm caches. Human time is dominated by reading and editing, which a scripted run cannot measure. The tutorial draft will be timed with a real first-time reader before the target is declared met.

CLI surface today: `sage db {status,upgrade}`, `sage plugin uninstall`, `sage validate`,
`sage schema export`. There is no command to create a world or a plugin, and no
`plugin install`. The `worlds` and `plugins` subcommands mentioned in the task do not exist.

Two fixes are too small to wait for this plan:
- **(a) Refuse to start without a JWT secret.** Today the server starts without one and returns
  500 on first registration.
- **(b) Add the secret step to the README quick start.**

Both are in the sequencing table.

## 3. The demo world and `sage world new <id>`

Two separate things, one per stage.

### 3a. The bundled demo world (Stage 1)

`worlds/demo/`: a four-room world that ships with the engine and is what `quickstart` runs when no
world is named. It is content, not a scaffold output, and it is authored and maintained in
WorldForge like any other world, so its `.positions.json` is the editor's own layout.

- **Rooms:** four, in one zone, laid out so every direction a newcomer tries early works: a start
  room with exits north, east and west, and one room beyond each. Plain, setting-neutral
  descriptions, one examinable feature per room. No items: placing an item in a room needs a
  plugin, and the demo enables none. Start and respawn are the first room.
- **Package:** the same files as Rivermoot, trimmed to what four rooms need: `world.toml`,
  `stats.yaml` (three neutral attributes, `hp`), `currencies.yaml` (one currency), `lexicon/en.yaml`
  (banner and motd that say this is the SAGE demo and point at the tutorial), `ui/theme.yaml`,
  `ai/style.yaml` with no prompts (narration off), `content.schema.json`, and a short `README.md`.
- **Plugins:** none enabled by default, with every first-party plugin listed as a comment in
  `world.toml` `[plugins]` with its one-line description. The tutorial turns one on.
- **Licensing:** FSL-1.1-ALv2 with the engine (`worlds/demo/LICENSE`) and a `NOTICE` entry, which
  `scripts/notice_check.py` requires (owner approved 2026-09-14).
- **Role next to Rivermoot:** Rivermoot stays the full proving ground (30 rooms, 10 plugins).
  The demo is the smallest world the engine accepts and the first thing a newcomer sees.
- `config/server.example.toml` defaults to `world = "demo"`, so the example config never boots the
  proprietary world.
- **Tests:** CI validates it (0 errors, 0 warnings), checks its exported schema is current, counts
  zero denylist hits, and the live smoke test plays it: start room, an exit and back, `say`,
  `who`, `quit`.

### 3b. `sage world new <id>` (Stage 2)

```
sage world new <id> [--name "My Town"] [--dir worlds] [--force]
```

**It creates a world package, not a map.** Rooms, exits and layout are drawn in WorldForge's map
builder; the command's job is to produce a package WorldForge can open and the engine can boot.

Generated tree:

```
worlds/<id>/
  README.md             what each file is for; next step: open it in WorldForge
  world.toml            [world] id, name, version = "0.1.0", engine = range of the installed engine
                        [start] room/respawn = "start:arrival"
                        [content] room_types, exit_dirs, equipment_slots = [] (the vocabulary
                        WorldForge offers when drawing)
                        [plugins] empty, every first-party plugin listed as a comment
                        [params] empty, with a commented example
  stats.yaml            three neutral attributes, vital hp, chargen attribute_points
  currencies.yaml       one currency, "coin"
  lexicon/en.yaml       banner and motd using the world name, stat/vital/currency names
  ui/theme.yaml         mark and accent (light and dark)
  ai/style.yaml         tone and rules; prompts/<slot>.j2 turns narration on
  content/world/zones/start/
    zone.yaml
    rooms/arrival.yaml  the single start room the engine requires: a name and a one-line
                        description, no exits, no features
  content.schema.json   exported by the same code as `sage schema export`
```

- **One room, no map.** The engine refuses a world without a start room, so exactly one is
  generated, with no exits and no `.positions.json`. Everything else about the map is made in
  WorldForge, which already writes rooms, exits and positions. Nothing here duplicates the editor.
- **Template source:** package data in `engine/src/sage/templates/world/`, Rivermoot-shaped (same
  files and keys), setting-neutral, scanned by the invariant ratchet with a test pinning zero
  denylist hits. It is not a stripped Rivermoot: section 2 measured how a copy drags the old
  world's identity through 10 files.
- **Values:** `<id>` must match `^[a-z][a-z0-9_]{1,31}$`; `--name` defaults to the id in title
  case; the engine range comes from the running engine; an existing directory is refused unless
  `--force`, which never deletes files the template does not produce.
- **Database:** not created. `world new` works offline and is testable without services. It prints
  the next steps: open the world in WorldForge, then `sage quickstart --world <id>` (or
  `sage db create --world <id> && sage db upgrade --world <id>` on an existing setup). One database
  per world stays the rule; its name defaults to `sage_<id>`.
- **Validation:** ends by running `sage validate --world <id>` in-process and exits non-zero on any
  error or warning, keeping the files for inspection.
- **WorldForge integration:** WorldForge gets a **New world** action that runs the same template
  (through `sage world new`, so there is one implementation), then opens the world's `start` zone
  with the arrival room on the canvas. Drawing rooms from there is the existing editor flow; its
  saves hot-reload into a running server.
- **Worlds in a clone of sage-engine:** `.gitignore` ignores `worlds/*` except the shipped worlds,
  so a user world is never an accidental `NOTICE` failure or commit. Keeping a world in its own
  repository uses `world_paths` from `FABLESTAR_PRIVATE_REPO_PLAN.md`.
- **Tests:** CI generates the template into a temporary directory, validates it, checks the
  exported schema, boots it hermetically, and runs WorldForge's vitest suite against it (the zone
  loads, a room can be added and saved, the result still validates).

## 4. `sage plugin new <id>`

```
sage plugin new <id> [--world <world>] [--with command,event,state,tick,panel,table]
```

### Location

- With `--world`, the plugin goes in `worlds/<world>/plugins/<id>/` and is enabled in that
  world's `world.toml` `[plugins]` (`<id> = "^0.1"`), with comments in the file preserved.
- Without `--world`, it goes in `plugins/<id>/`, the first-party location, for engine
  contributors.
- The tutorial always uses `--world`.

### Generated files

```
<id>/
  plugin.toml
  sage_plugin_<id>/__init__.py
  sage_plugin_<id>/main.py     def setup(api: PluginAPI) -> None
  lexicon/en.yaml
  tests/test_<id>.py           loads the plugin through the public test host, runs its command
  README.md                    what [touches] is, and the loop: register -> declare -> check
```

### The manifest

The manifest is the hard part, so the scaffold is built to teach it.
- **A single table** in the scaffold code maps each feature to three things: the code snippet in
  `main.py`, the `[touches]` entries it needs, and a one-line explanation. The generated code and
  its manifest therefore cannot disagree.
  - The default feature, `command`, registers `api.commands.register("<id>", …)` with text from
    `api.t("<id>.…")`. It declares `commands = ["<id>"]` and `lexicon_prefix = "<id>."`.
  - `--with state` adds `api.state.block` and `state_blocks`.
  - `--with event` adds a subscriber and `events_subscribe`.
  - `--with tick` adds `api.tick.every` and `tick_jobs`.
  - `--with panel` adds `api.ui.panel` plus `api.snapshot.contribute`, and `panels` plus `snapshot`.
  - `--with table` adds a migrations directory with a first `plg_<id>_` revision, and `tables`.
- **Every other `[touches]` key** that this engine supports (`sage.plugins.manifest.Touches`) is
  written as a comment with an empty value, a one-line explanation and the `api.` call that needs
  it:
  ```toml
  # tick_jobs = []   # names passed to api.tick.every(seconds, fn, name=...)
  ```
  The manifest documents the whole capability model in the place a developer reads it.
- `first_party = false`. `version = "0.1.0"`. `engine` is derived from the installed engine, as
  in `world new`.

### Verification

**The command ends by loading the plugin through the real seal.** It uses `registration_host` for
the target world, or for a throwaway copy of the template world when there is no `--world`.
- It exits non-zero if the manifest refuses anything, so a scaffold that fails the capability check
  can never be left on disk silently.
- The seal's existing error already names the kind, the names and the `plugin.toml` path
  (`loader.py:179`).

### Follow-up in the same item: `sage plugin check <id> [--world]`

This runs the same offline load for a plugin the developer has since changed. It turns "I added a
command and boot fails" into a one-line answer:
- *registered commands ['greet'] not declared in [touches].commands of …/plugin.toml*

It also warns about keys declared but never registered, so manifests do not accumulate stale
grants.

### Prerequisite: a public test host

Today `plugin_host(...)` lives in `engine/tests/fakes.py`, which is not importable outside the
repository. Generated tests need a supported one.
- Proposal: `sage.testing.plugin_host(world, [ids])` and `sage.testing.fake_session()`, exported
  and versioned like `sage.api`.
- Size: S. The code exists; this is a stable name and docs.

The scaffold never generates an import from anything but `sage.api` (and `sage.testing` in tests),
and the existing import-boundary check covers generated code. It is run on the scaffold's output
in CI.

## 5. Plugin distribution: position

**Decision: filesystem placement stays the model for now. There is no `sage plugin install` in
this plan.** The supported ways to get a plugin are:
1. **World-only plugins** live in the world package (`worlds/<world>/plugins/<id>`) and travel
   with it. This is how most authors will share mechanics, since a world and its rules are
   usually shipped together.
2. **Shared plugins** are directories under `plugins/`, obtained however the author distributes
   source (git clone, git submodule, copying a directory). `world.toml` pins a version range
   (`combat = "^1"`), and boot refuses a mismatch.

Reasoning:
- **There is nothing to install from yet.** A registry needs publishers, naming rules, trust and
  review. Two first-party worlds and no third-party plugins cannot justify that, and the two-world
  ceiling from Phase 1 applies.
- **`install <git-url>` would be `git clone` plus a manifest check**, and it would imply a trust
  decision the engine cannot make. A plugin is arbitrary Python running in the server process.
  `[touches]` limits what it registers, not what its code does. An install command that looks
  safe is worse than a copy that is plainly "run this code".
- **What the engine owes a plugin author today** is an unambiguous directory layout, version pins
  that boot enforces, a scaffold, and `sage plugin check`. Those are in this plan.

Revisit when the first external plugin exists. The likely next step is `sage plugin install <path|git-url>`, which would:
- place the plugin directory
- run `plugin check`
- apply its migrations
- add it to `world.toml`

It would print that plugin code runs with full server privileges. `plugin uninstall` already
exists, so install is the missing half, not a new concept.

## 6. Tutorial outline

Two documents, one per stage. The reader knows a terminal and nothing about MUDs. Each step ends
with something they can see.

### `docs/tutorial/01-run-the-engine.md` (Stage 1)

1. **What you are running (2 min).** A text world is rooms joined by exits; players type commands.
   SAGE splits it three ways: the engine runs things, a world package holds places, words and
   look, plugins add rules. One diagram.
2. **Install and start (5 min).** Commands 1–4 from section 1, and what `quickstart` did: services
   in Docker, config generated with local-only settings, the demo world's database, the player
   client built.
3. **Walk the demo (2 min).** Press **Play**; `look`, `north`, `south`, `examine tree`,
   `say hello`, `help`. What a room line and exits mean.
4. **Change a room (1 min).** Edit a demo room's `description.base`, save, `look`. It changes
   without a restart, and no engine file was touched.
5. **Where next.** Stage 2 tutorial; Rivermoot as a full example; `docs/architecture.md`.

### `docs/tutorial/02-build-a-world.md` (Stage 2)

1. **Make a world (2 min).** WorldForge → **New world** (or `sage world new mytown`), then read the
   generated `README.md`: which file holds what.
2. **Draw the map (8 min).** In WorldForge's map builder, add rooms around the arrival room,
   connect exits, write descriptions, save. `sage validate --world mytown`; break an exit on
   purpose to read a real error, then fix it.
3. **Play it (2 min).** `sage quickstart --world mytown`, press **Play**, walk what you drew. Edit a
   room in WorldForge while connected and `look`.
4. **Rename a stat and a currency (2 min).** Change labels in `lexicon/en.yaml`, reconnect, see the
   character sheet and wallet change. The world owns its words; the engine only knows keys.
5. **Turn on a mechanic (3 min).** Uncomment `consumables` in `world.toml`, add a `heal:` item and
   a spawn in WorldForge, restart, `use` it.
6. **Write a tiny plugin (5 min, optional).** `sage plugin new wave --world mytown`, read the
   generated `plugin.toml` comments, restart, `wave`. Add a second command without declaring it,
   watch `sage plugin check` name the missing line, then add it.

Both are timed with at least one real first-time reader before the targets in section 1 are
declared met.

## 7. Infrastructure for a first run

| Option | What it takes | Verdict |
|---|---|---|
| **A. `sage quickstart` wrapping Docker Compose** | One command (`--world` defaults to the demo world): check Docker; generate `.env` (random DB password), `server.toml` (JWT secret, `world`, `dev_mode`, `dev_login`) and `database.toml` when absent; `docker compose up -d`; wait for health; `db create`; `db upgrade`; build the player client if `dist/` is missing or stale; start Nexus serving it. | **Recommended.** S–M. Same Postgres and Redis as production and CI, so nothing a newcomer builds behaves differently later. |
| B. SQLite / in-memory dev mode | A second persistence backend. The engine uses Postgres JSONB and 16 Postgres-specific references in `engine/src` and `engine/alembic`; plugins ship Alembic branches written for Postgres; every hot path goes through Redis. | **Rejected.** L–XL, and a permanent second code path. It contradicts the two-tier testing ruling: persistence is proven on real databases because fakes hid migration failures before. The hermetic fakes stay a test tool, not a runtime. |
| C. Compose-only (`docker compose up` runs everything, config baked in) | Containerize the server and clients, seed config at container start. | Rejected as the first-run path. Hot reload across a bind mount is slow on Windows and macOS, and debugging moves into containers. It is worth doing later as the **deployment** image. |

`quickstart`, in detail:
- **Idempotent.** A second run starts what is stopped and changes no existing config file. It
  prints exactly which files it wrote.
- **Generated secrets never print.** It writes `.env` and the TOML files, which are gitignored.
- **Builds on dev auth rather than adding a new path.**
  - It sets `dev_mode = true` and `dev_login = true`, so the first page offers **Play** without
    an account (loopback only).
  - The lines that write `dev_login` sit inside `DEV-AUTH` markers, so a stripped release's
    quickstart writes only `dev_mode`. Then the player registers normally.
- **One terminal.**
  - Nexus serves the built player client at `/` when `engine/clients/player-ui/dist` exists.
    That is a small static mount, next to the portrait mounts.
  - The admin console stays a separate dev server for people who need it.
  - `quickstart --admin` also starts it, and creates a head admin through dev auth.
- **Failure messages name the fix:** Docker not running, a port in use (it suggests `--port`), or
  Node missing for the first client build.
- **It never touches an existing database's data.**

## 8. Sequencing

Ordered by adoption impact per unit of effort, Stage 1 first. Sizes: XS under half a day, S about a
day, M two to four days, L a week or more.

| Order | Item | Stage | Size | Impact |
|---|---|---|---|---|
| 1 | **Fail fast without a JWT secret, and fix the README quick start.** The server refuses to start with a message saying how to generate one. | 1 | XS | Removes the silent 500 every newcomer hits today. |
| 2 | **Demo world** `worlds/demo/` (four rooms, drawn in WorldForge), `server.example.toml` defaults to it, CI validate and live smoke | 1 | S | A first world that is small, licensed and not proprietary. Needs the owner's license decision for the new path. |
| 3 | **`sage quickstart`**: config generation, compose, `db create`, `db upgrade`, dev-auth defaults, runs the demo | 1 | S–M | 18 commands to about 7, zero hand edits. **The single item that most improves a stranger's first hour.** |
| 4 | Nexus serves the built player client at `/` (quickstart builds it) | 1 | S | 3 terminals to 1; Stage 1 reaches its 5-command target. |
| 5 | Stage 1 tutorial, timed with a real reader | 1 | XS–S | Needs 2–4. |
| 6 | `sage world new` (package plus one start room), validate on exit, `sage db create --world`, CI template tests | 2 | S–M | Smaller than the first draft: no generated map. |
| 7 | WorldForge **New world** action over the same template | 2 | S | World building starts in the tool that draws the map. |
| 8 | Stage 2 tutorial, timed | 2 | S | Needs 6–7. |
| 9 | `sage.testing` public test host, then `sage plugin new` plus `sage plugin check` | 2 | S + M | Makes the manifest self-teaching. |
| 10 | `world_paths` (shared with the Fablestar move plan) | 2 | S–M | User worlds in their own repositories. |
| 11 | Revisit `sage plugin install` when a first external plugin exists | — | — | Section 5. |

Item 1 is small enough to ship before the rest is approved, if the owner wants. Item 2 needs the
owner's licensing call for `worlds/demo/`. Status 2026-09-14: owner approved the plan and FSL for the demo; items 1 and 2 are done.

