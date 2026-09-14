# Zero to first world: onboarding plan

Status: **proposal, awaiting owner review.** Nothing in this document is implemented. Scaffold
work starts only after it is approved.

SAGE's seams hold: `sage.api` is the only import surface for plugins, `[touches]` seals what a
plugin may do, and Rivermoot runs a different world on the same engine code. What is missing is
the road from a stranger's `git clone` to their own running world. This plan measures that road
as it is today, sets a target, and designs the commands and the tutorial that get there.

---

## 1. Target experience

**Success:** a newcomer goes from `git clone` to walking around a three-room world they created,
and changes something they can see, in **under 15 minutes of wall-clock time, with 6 commands, one
terminal, and no file edited by hand before they first play.**

Prerequisites: Python 3.11+, Node.js LTS, Docker, and Git are already installed. Installing them is
outside this budget, as it is for every engine's getting-started page.

```bash
git clone https://github.com/Fablestarexpanse/sage-engine && cd sage-engine   # 1
python -m venv .venv && . .venv/bin/activate                                   # 2  (Windows: .venv\Scripts\activate)
pip install -e ./engine                                                        # 3
sage world new mytown                                                          # 4
sage quickstart --world mytown                                                 # 5  services, config, database, client build, server
# 6: open http://localhost:8001, press "Play", walk around.
```

Then, in the tutorial, edit `worlds/mytown/content/world/zones/start/rooms/courtyard.yaml` and type
`look` to see the change appear without a restart.

Why these numbers:
- **15 minutes.** The unavoidable machine time is short. Measured in section 2, the engine install
  takes 49–54 s, the client installs 3–10 s, and the services, migrations and first boot under 10 s.
  Cold Docker image pulls add about a minute, which was not measured because the images were
  cached. That leaves more than 10 minutes for reading the tutorial and for a first
  `pip install` on a slow connection. A 5-minute target would only be met by people who skip the
  tutorial, and the tutorial is where the world/engine split is learned.
- **6 commands.** Today's path is 18 (section 2). Commands 1–3 are standard for any Python project
  and cannot be removed without a packaged release. Commands 4 and 5 are the two new ones, and
  opening the browser is the sixth. Every further step belongs inside `quickstart`, because each
  one is a place a newcomer can go wrong.
- **One terminal and zero hand edits before first play.** Today it is 3 terminals and 5 edits,
  one of which is undocumented and fails silently (section 2). Configuration a newcomer does not
  understand yet must be generated, not typed.

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

## 3. `sage world new <id>`

```
sage world new <id> [--name "My Town"] [--dir worlds] [--force]
```

### Template

A **purpose-built minimal world**, not a stripped Rivermoot. It is shipped as package data in
`engine/src/sage/templates/world/`, under the engine's license.
- Stripping Rivermoot produces the problem measured above: its identity is spread across 10 files
  and would have to be scrubbed by rewrite rules that break whenever Rivermoot changes.
- Rivermoot keeps its job: the full proving ground with 30 rooms and 10 plugins.
- The template is **Rivermoot-shaped**: the same files, the same keys, the same content model.
  Nothing new is invented, and a CI test keeps the two structurally in step (see "Tests").

### Generated tree

```
worlds/<id>/
  README.md             what each file is for, and what to change first
  world.toml            [world] id, name, version = "0.1.0", engine = range of the installed engine
                        [start] room/respawn = "start:courtyard"
                        [content] room_types, exit_dirs (8 directions), equipment_slots = []
                        [plugins] empty, with every first-party plugin listed as a comment:
                        its id and the one-line description from its plugin.toml
                        [params] empty, with a commented example
  stats.yaml            3 neutral attributes (label keys), vital hp, chargen attribute_points
  currencies.yaml       one currency, "coin"
  lexicon/en.yaml       login banner and motd using the world name, stat/vital/currency names
  ui/theme.yaml         mark and accent (light and dark)
  ai/style.yaml         tone and rules, with a comment that prompts/<slot>.j2 turns narration on
  content/world/zones/start/
    zone.yaml
    rooms/courtyard.yaml, hall.yaml, garden.yaml   three rooms, two-way exits, one feature
                                                   each, plain descriptions
    .positions.json     from sage.world.layout, so maps and WorldForge draw it at once
  content.schema.json   exported by the same code as `sage schema export`
```

- No `plugins/` directory until `sage plugin new` creates one. No `LICENSE`: that is the author's
  choice, and the README says so.
- All generated text is setting-neutral: no genre, no proper nouns beyond the world name. Template
  files sit under `engine/`, so the invariant ratchet scans them, and a test pins the denylist count
  at zero for `templates/`.

### Values

- `<id>` must match `^[a-z][a-z0-9_]{1,31}$` (a directory name, Redis prefix and database suffix).
- `--name` defaults to the id in title case.
- The engine range is derived from the running engine version (`>=0.2,<0.3`), so a scaffold never
  claims a range the engine refuses.
- An existing directory is refused unless `--force` is given, and `--force` never deletes files
  that the template does not produce.

### Database

**It does not create a database or run migrations.** `world new` works offline, runs in under a
second, and is testable without services.
- Its last lines print the next command, `sage quickstart --world <id>`, or for an existing setup,
  `sage db create --world <id> && sage db upgrade --world <id>`.
- A small new `sage db create` turns today's undocumented `createdb` step into a command.
- One database per world stays the rule (owner ruling). The database name defaults to
  `sage_<id>`, and `db`, `quickstart` and the server derive it from `--world` when
  `database.toml` does not set one.

### Validation

**It ends by running `sage validate --world <id>` in-process** and exits non-zero if there is any
error or warning. The files are kept, so the output can be inspected.
- A scaffold that produced a broken world would fail loudly on the machine that made it, not
  later in the tutorial.
- CI makes it impossible to ship such a template in the first place (see "Tests").

### Worlds in a clone of sage-engine

`scripts/notice_check.py` fails on a world package that `NOTICE` does not list. So that a
newcomer's world is never an accidental licensing problem, `.gitignore` ignores `worlds/*` except
the reference worlds. A user world stays untracked in the engine repository.
- The tutorial's last section shows how to keep the world in its own repository.
- That uses the `world_paths` setting from `FABLESTAR_PRIVATE_REPO_PLAN.md` (prerequisite 1),
  which serves both needs.

### Tests

For every template, CI does the following:
- generates it into a temporary directory, then:
  - runs validate with 0 errors and 0 warnings
  - checks that the exported schema equals the generated `content.schema.json`
  - loads it through `sage.plugins.offline.registration_host`
  - boots it hermetically on the fakes and walks `north`/`south`
- counts ratchet hits for `templates/` (must be 0)
- runs a structural check that every top-level key and file in Rivermoot also exists in the
  template, or is listed as intentionally absent.

The live tier adds a smoke test that runs quickstart's steps against Docker and plays the
template world.

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

## 6. "Your first world" tutorial outline

`docs/tutorial/first-world.md`. The reader knows a terminal and nothing about MUDs. Each step ends
with something they can see.

1. **What you are building (2 min).**
   - A text world is rooms joined by exits, and players type commands.
   - SAGE splits it three ways: the engine runs things, the world package holds your places,
     words and look, and plugins add rules.
   - One diagram of the three.
2. **Install and start (5 min).** Commands 1–5 from section 1. Explains what `quickstart` did:
   - services started in Docker
   - config generated with local-only settings
   - database created
   - the player client built
3. **Walk around (2 min).**
   - Press **Play**; `look`, `north`, `south`, `say hello`, `help`.
   - What a room line and exits mean.
4. **Change a room (2 min).**
   - Edit `courtyard.yaml` `description.base`, save, type `look`. It changes without a restart.
   - Point out that no engine file was touched.
5. **Add a room (3 min).**
   - Create `fountain.yaml` and add an exit from `garden` to `fountain` and back.
   - Run `sage validate --world mytown`. Break it on purpose (a misspelled destination) to read a
     real error, then fix it.
6. **Rename a stat and a currency (2 min).**
   - Change the attribute label in `lexicon/en.yaml` and the currency name. Reconnect and see the
     character sheet and wallet change.
   - The world owns its words; the engine only knows keys.
7. **Turn on a mechanic (3 min).**
   - Uncomment `consumables` in `world.toml`, add a `heal:` item and a room spawn, restart, pick up
     the item and `use` it.
   - First look at a plugin as rules you can switch on.
8. **Write a tiny plugin (5 min, optional).**
   - `sage plugin new wave --world mytown`, read the generated `plugin.toml` comments, restart,
     type `wave`.
   - Add a second command without declaring it, watch `sage plugin check` name the missing line,
     then add it.
9. **Where next.**
   - WorldForge for drawing maps.
   - Rivermoot as a full example.
   - Keeping your world in its own repository (`world_paths`).
   - `docs/architecture.md`.

Timed with at least one real first-time reader before the target in section 1 is declared met.

## 7. Infrastructure for a first run

| Option | What it takes | Verdict |
|---|---|---|
| **A. `sage quickstart` wrapping Docker Compose** | One command: check Docker; generate `.env` (random DB password), `server.toml` (JWT secret, `world`, `dev_mode`, `dev_login`) and `database.toml` when absent; `docker compose up -d`; wait for health; `db create`; `db upgrade`; build the player client if `dist/` is missing or stale; start Nexus serving it. | **Recommended.** S–M. Same Postgres and Redis as production and CI, so nothing a newcomer builds behaves differently later. |
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

Ordered by adoption impact per unit of effort. Sizes: XS under half a day, S about a day, M two to
four days, L a week or more.

| Order | Item | Size | Impact |
|---|---|---|---|
| 1 | **Fail fast without a JWT secret, and fix the README quick start.** The server refuses to start with a message saying how to generate one. | XS | Removes the silent 500 every newcomer hits today. |
| 2 | **`sage quickstart`**: config generation, compose, `db create`, `db upgrade`, dev-auth defaults, then run. | S–M | 18 commands to about 8, 3 terminals to 2, zero hand edits. **The single item that most improves a stranger's first hour.** |
| 3 | Nexus serves the built player client at `/` (quickstart builds it) | S | 2 terminals to 1. |
| 4 | Example config defaults to Rivermoot, not the proprietary world | XS | First impression is a licensed world. Also a step in the Fablestar move plan. |
| 5 | `sage world new` with the minimal template, validate on exit, CI template tests, `sage db create` | M | Own world with no copying or scrubbing. |
| 6 | Tutorial `docs/tutorial/first-world.md`, timed with a real reader | S | Makes the split felt. Needs 2 and 5. |
| 7 | `sage.testing` public test host | S | Prerequisite for 8. |
| 8 | `sage plugin new` plus `sage plugin check` | M | Makes the manifest self-teaching. |
| 9 | `world_paths` (shared with the Fablestar move plan) | S–M | User worlds in their own repositories. |
| 10 | Revisit `sage plugin install` when a first external plugin exists | — | Section 5. |

Items 1 and 4 are small enough to ship before the rest is approved, if the owner wants. Everything
from item 2 on waits for review of this plan.
