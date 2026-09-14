# Moving Fablestar Expanse to a private repository

Owner decision (2026-09-14, `DECISIONS.md`): `worlds/fablestar/` moves out of the public
`sage-engine` repository into a private one. This is the plan; nothing below is done yet except
where marked.

## What the move does and does not achieve

- It makes the proprietary boundary physical: future Fablestar content, lore and design work never
  land in the public repository, and forks stop receiving about 1 MB of material they have no
  right to use.
- It does **not** un-publish anything. Every Fablestar file is already in the public git history
  and in any existing clone. Rewriting public history (for example `git filter-repo` plus a force
  push) is a separate owner decision, and it breaks every fork and clone. This plan does not
  include it.

## Prerequisites (engine and tests)

1. **A world can live outside `worlds_dir`.** Today `select_world(root / server.worlds_dir, world)`
   looks in one directory only (`engine/src/sage/world/package.py:267`), and `available_worlds`
   lists that directory. `worlds_dir` may be an absolute path, but then Rivermoot would have to
   move too.
   - Proposed: `server.world_paths` (a list of directories, default `["worlds"]`). Each entry is
     either a world package (it has `world.toml`) or a directory of packages. `available_worlds`
     and `select_world` search them in order; a duplicate world id is a boot error.
   - Every caller moves to the new lookup: `server.py:89`, `cli.py` (three sites), live test
     helpers, and the WorldForge and worldforge-mcp world pickers.
   - World-only plugins (`worlds/<id>/plugins/`) already resolve relative to the package, so they
     move with it.
   - Size: S–M.
2. **First-party plugin tests stop reading Fablestar content.** `engine/tests/fakes.py:269`
   `repo_world()` returns the package with the most rooms, which is Fablestar. Eighteen test
   files use it (`engine/tests/plugins/test_*_plugin.py` for achievements, agents, ambient,
   combat, consumables, crafting, effects, equipment, factions, hazards, lodging, maestro,
   missions, search and shop; `test_agents_body.py`, `test_factions_host.py`,
   `test_events_resolvers.py`).
   - Proposed: a small, setting-neutral fixture world under `engine/tests/fixtures/worlds/`,
     licensed with the engine. It carries just enough agents, factions, maestro events and rooms
     for those tests. `repo_world()` returns it explicitly instead of picking by room count.
   - Size: M. This is the largest part of the move.
3. **CI keeps proving two worlds.** The live smoke test parametrizes over `available_worlds`, so
   the public CI would drop to Rivermoot alone. The brief's invariant ("a second, different world
   boots on unchanged engine code") needs a second world in public CI.
   - The fixture world from step 2 can take that role.
   - The private repository runs its own CI against a pinned engine version.

## The move

1. **Owner:** create the private repository (for example `Fablestarexpanse/fablestar-world`). I
   will not create or rename repositories through the API.
2. Export `worlds/fablestar/` and `docs/design/` with history into it:
   `git filter-repo --path worlds/fablestar --path docs/design --path-rename worlds/fablestar/:`.
   Do this in a scratch clone, never in the working repository.
3. The private repository gets its own CI:
   - check out `sage-engine` at a tag
   - `pip install -e engine`
   - point `world_paths` at the checkout
   - run the conduit and morality plugin tests and the live smoke test
4. In `sage-engine`, one commit:
   - delete `worlds/fablestar/`, `docs/design/` and `docs/screenshots/player-client-fablestar.png`
   - update `NOTICE`; `scripts/notice_check.py` fails until the entries match
   - change `config/server.example.toml` to `world = "rivermoot"`
   - update the README world table and the screenshots
5. **Local development of both:** clone the private repository next to `sage-engine` and set
   `world_paths = ["worlds", "../fablestar-world"]` in `config/server.toml`, which is gitignored.
   A git submodule is the alternative. It pins versions but makes every public clone see a
   submodule it cannot fetch, so a sibling checkout is recommended.
6. Remove the Fablestar-specific terms from `scripts/sage_denylist.toml` only if they can no
   longer leak. They should stay, since the engine must still never name them.

## Order and sizing

| Step | Size | Blocks |
|---|---|---|
| Prerequisite 1: `world_paths` | S–M | the move |
| Prerequisite 2: fixture world for plugin tests | M | the move |
| Prerequisite 3: second world in public CI | S (after 2) | the move |
| Owner creates private repository | owner | the move |
| Export with history, private CI | S | public deletion |
| Public deletion commit, NOTICE, README, example config | S | — |

Until the move lands, `NOTICE` states that `worlds/fablestar/` is proprietary, unlicensed, and in
the public repository only until it moves.
