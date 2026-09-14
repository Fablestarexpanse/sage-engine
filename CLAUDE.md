# CLAUDE.md — SAGE (Synthetic Agent Game Engine)

Conventions for AI coding agents working in this repository. For how the system works, read
these first; this file does not repeat them:

- `docs/architecture.md` — the canonical architecture: engine, world packages, plugins, state,
  AI, clients, configuration, development setup and testing.
- `docs/sage/PHASE1_CONTRACTS.md` — the approved contracts for world packages and plugins.
- `docs/sage/DECISIONS.md` — every ruling since; when any doc disagrees with it, it wins.
- `docs/dev/STANDARDS.md` — the engineering Definition of Done.

---

## Rules

- **Do not add world-specific code to the engine.** Put the term in a world package, the text
  behind a lexicon key, the mechanic in a plugin. The invariant ratchet enforces it.
- **Never raise a ratchet baseline** (`scripts/sage_invariants_baseline.json`) to make CI pass.
  When you remove hits, run `python scripts/sage_invariants.py update` to lock in the lower count.
- **Plugins import only `sage.api`** and declare every touch in `plugin.toml` `[touches]`. Never
  bypass the manifest seal or the import boundary, including in generated or scaffolded code.
- **Engine player text goes through the lexicon** (`session.say("key", ...)` plus a default in
  `engine/src/sage/lexicon/en.yaml`); a literal `session.send("...")` fails the ratchet.
- **Do not modify `worlds/fablestar/`** unless the task is about Fablestar content. It is
  proprietary (see `NOTICE`).
- **Dev-only auth code stays inside `DEV-AUTH` markers** (`docs/dev/DEV_AUTH.md`);
  `scripts/release_check.py` strips it for release.
- **Every top-level path and world package needs a `NOTICE` entry**; `scripts/notice_check.py`
  fails CI otherwise. A new directory is a licensing decision for the owner, not a default.
- **Migrations and persistence are tested on the live tier**, never against fakes alone. Never
  weaken `test_models_match_migrations`; fix the model or add a migration.

## Before committing

```bash
python -m ruff format engine/src engine/tests plugins worlds
python -m ruff check engine/src engine/tests plugins worlds
python scripts/sage_invariants.py check
python scripts/notice_check.py
python -m pytest
SAGE_LIVE_TESTS=1 python -m pytest -m live     # when servers, migrations, persistence or smoke-played plugins change
(cd engine/tools/worldforge && npx vitest run)  # when WorldForge changes
```

Run the whole suite, not only the tests near your change. Stage explicit paths: the working tree
often holds the owner's uncommitted work.

## Key patterns to follow

- **World data, not engine code** — room types, attributes, currencies, words, prompts and looks belong to the world package; mechanics belong to plugins.
- **Declare before you touch** — every command, event, resolver, state block, content field, panel, route, table, Redis prefix and AI slot a plugin uses is listed in its `plugin.toml` `[touches]`.
- **Lazy `app_instance` imports inside engine handlers** — avoids circular imports at module load time.
- **Never block the game loop** — all game code is `async`. Network I/O, DB queries, and LLM calls must be `await`-ed.
- **LLM failures are non-fatal** — send the deterministic outcome first, narrate after, and treat any exception (including `SlotDisabled`) as "no prose".
- **Redis for speed, Postgres for durability** — update Redis immediately; PersistenceManager handles the Postgres write asynchronously.
- **Room ID format** — always `zone_id:room_slug`. The slug is the YAML file stem.
- **WorldForge and the worldforge-mcp tools both write zone files directly** (last write wins);
  don't edit the same zone through both at once.

## Local agent workflow

Some developers run the rexyMCP architect/executor workflow. Its config (`rexymcp.toml`) and
contract (`REXYMCP.md`) are local, gitignored files, imported below when present.

@REXYMCP.md
