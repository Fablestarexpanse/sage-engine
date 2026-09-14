# Tutorial 1: Run the engine

About 10 minutes. By the end you will have SAGE running on your machine, you will have walked
around its demo world in a browser, and you will have changed a room while the server was running.

You need to know how to use a terminal. You do not need to know anything about MUDs or game
engines.

## What you are running

A **text world** is a set of **rooms** joined by **exits**. A player is always in one room. They
read its description and type commands such as `north` or `look`, and the world answers in text.
Many people can be in the same world at once.

SAGE keeps three kinds of thing apart:

```
  engine          runs the world: connections, commands, saving, timing
  world package   the places, words, stats and look of one world    (worlds/<name>/)
  plugins         extra rules a world can switch on: combat, shops… (plugins/<name>/)
```

The engine knows nothing about any particular world. In this tutorial you run the engine with the
**SAGE Demo** world: four rooms and no plugins.

## 1. Check the prerequisites

Install these first if you don't have them:

- **Python 3.11 or newer**: `python --version`
- **Node.js LTS**: `node --version` (builds the web page you play in)
- **Docker**: `docker --version`, and Docker Desktop running (it runs the databases)
- **Git**: `git --version`

## 2. Install and start (about 5 minutes)

Get the code and install the engine into its own Python environment.

macOS and Linux:

```bash
git clone https://github.com/Fablestarexpanse/sage-engine
cd sage-engine
python -m venv .venv
. .venv/bin/activate
pip install -e ./engine
```

Windows (PowerShell):

```powershell
git clone https://github.com/Fablestarexpanse/sage-engine
cd sage-engine
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ./engine
```

If PowerShell refuses to run `Activate.ps1` ("running scripts is disabled on this system"), run
`Set-ExecutionPolicy -Scope Process RemoteSigned` first. It only affects that terminal window.

Then start everything with one command:

```bash
sage quickstart
```

It prints six steps:

```
[1/6] config for world 'demo'
      wrote .env
      wrote config/server.toml
      wrote config/database.toml
[2/6] starting Postgres and Redis (docker compose)
[3/6] database 'sage_demo' created
[4/6] applying migrations
[5/6] player client built
[6/6] starting the server for 'demo' (Ctrl+C stops it)
      open http://localhost:8001/ and press Play
```

What it did:

1. **Config.** It wrote three settings files with a generated database password and a secret for
   signing logins. They are yours now; quickstart never overwrites them. These are local-only
   settings: they let this machine log in without a password, so never put this setup on a
   network.
2. **Services.** It started PostgreSQL (where characters are saved) and Redis (where the live
   state of the world is kept) in Docker.
3. **Database.** It created a database for the demo world. Each world gets its own.
4. **Migrations.** It set up the database tables.
5. **Player client.** It built the web page you play in.
6. **Server.** It started the SAGE server. Leave this terminal open; the log scrolls here.

If a step fails, the message says what to do. The common ones:

- *Docker is not installed or not on PATH*, or *Is Docker running?*: start Docker Desktop, then run
  `sage quickstart` again.
- *port is already allocated*: something else uses port 5432 or 6379, often another PostgreSQL or
  Redis. Stop it, or see `sage quickstart --help` for `--no-docker`.

Running `sage quickstart` again later is safe. It skips everything that is already done and starts
the server.

## 3. Walk the demo (about 2 minutes)

Open **http://localhost:8001/** in a browser. Click **Sign in**. Under **Dev login (no password,
localhost only)** leave the name as it is and press **Play**.

You are standing in **The Commons**:

```
The Commons [ start:commons ]
A small square of swept flagstones with a stone bench at its centre. Paths lead north to a garden, east to a workshop and west to a reading room.
Exits: north, east, west
```

- The first line is the room's name, then its **id** in brackets. `start` is the zone (a group of
  rooms) and `commons` is the room.
- **Exits** are the directions you can go.

Type these into the command box at the bottom, pressing Enter after each:

| Command | What happens |
|---|---|
| `look` | describes the room again |
| `examine bench` | a closer look at something the room mentions |
| `north` | walks through the north exit, to the Walled Garden |
| `south` | back to The Commons |
| `say hello` | speaks to everyone in the room |
| `who` | lists who is connected |
| `help` | lists every command |

Try `west` and `examine books` too.

## 4. Change a room (about 1 minute)

Everything you just read comes from files in `worlds/demo/`. Nothing in the engine mentions a
garden or a bench.

Open `worlds/demo/content/world/zones/start/rooms/commons.yaml` in any text editor. Near the top:

```yaml
description:
  base: A small square of swept flagstones with a stone bench at its centre. Paths lead north to a garden, east to a workshop and west to a reading room.
```

Change the text after `base:` to anything you like, for example:

```yaml
  base: A small square, freshly painted blue. Paths lead north to a garden, east to a workshop and west to a reading room.
```

Save the file. Go back to the browser, walk back to The Commons if you left it, and type `look`.
Your new description appears. You did not restart anything: the server noticed the file change
and reloaded the room.

### If `look` says "You are in the void."

The server could not read the room file, and it logs why in its terminal:

```
[ERROR] sage.world.loader: Error loading room start:commons: mapping values are not allowed here
  in "…/rooms/commons.yaml", line 6, column 23
```

The most common cause is a **colon followed by a space** inside your text, for example
`A small square: freshly painted`. In YAML that starts a new key. Put the whole text in double
quotes:

```yaml
  base: "A small square: freshly painted blue."
```

Save again and type `look`: the room comes back, still without a restart.

You can also check a world without the server. In a second terminal, in the `sage-engine` folder
with the environment activated:

```bash
sage validate --world demo
```

It lists every problem, starting with the file that failed to load, and ends with a count such as
`demo (3 rooms): 6 error(s), 2 warning(s)`. The other errors follow from the first one (rooms
whose exits lead to the room that failed), so fix the first line and run it again until it says
`demo (4 rooms): 0 error(s), 0 warning(s)`.

## 5. Stop and start again

- **Stop:** press `Ctrl+C` in the terminal running the server. PostgreSQL and Redis keep running in
  Docker; `docker compose stop`, run in the `sage-engine` folder, stops them too.
- **Start again:** `sage quickstart`, or just `sage` (the server alone) when Docker is already up.

## Where next

- **Tutorial 2: build a world** (coming next): make your own world package and draw its map in
  WorldForge.
- **Rivermoot** (`worlds/rivermoot/`) is a full example world: 30 rooms, a shop, fights and
  levels. Run it with `sage quickstart --world rivermoot`.
- **How SAGE fits together:** [`docs/architecture.md`](../architecture.md).
