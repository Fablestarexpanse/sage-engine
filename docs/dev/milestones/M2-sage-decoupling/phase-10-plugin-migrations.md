# Phase 10: Plugin-owned migrations and uninstall

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** phase-08
**Tags:** language=python, kind=feature, size=m

## Goal

Locked decision 8 and contracts D.D / C.3: plugins may own tables through their own alembic
branches, the server never auto-migrates and refuses to boot while migrations are pending, and a
plugin can be uninstalled cleanly including its schema.

## Spec (as built)

1. Core chain labelled `sage_core` (empty revision `m6n7o8p9q0r1`).
2. `sage.plugins.migrations`: `alembic_config(plugin_paths)` (core + each plugin's
   `migrations/versions`), `pending_heads[_async]`, `unexpected_tables_async` (warns about tables
   neither core nor `plg_<enabled plugin>_*`), `is_core_object` autogenerate filter (env.py).
3. `SageServer.startup`: discover plugins → refuse to start on pending heads with the exact
   command → warn on stray tables → load plugins.
4. `sage.plugins.uninstall`: refuse when a required dependent is enabled; downgrade
   `plg_<id>@base`; `--purge-state` removes the plugin's declared state blocks from every
   character and agent stats blob; remove the entry from `world.toml` keeping comments.
5. `sage.cli` / `python -m sage`: run server (default), `db status`, `db upgrade`,
   `plugin uninstall ID [--purge-state]`; console scripts point at `sage.cli:run`.

## Update Log

### Update — 2026-09-13 (complete)

Hermetic 431 passed; 5 new unit tests (version locations, autogenerate filter, dependents,
manifest edit keeping comments, core label). Live tier 8 passed, including a real plugin with a
migration: pending detected → `upgrade heads` creates `plg_ledger_entries` → uninstall with
`--purge-state` drops the table, strips the `ledger` block from a character row and removes the
plugin from world.toml. Real runs: `python -m sage` against the dev DB refused with "Database
'fablestar' is missing migrations (unapplied heads: m6n7o8p9q0r1). Run: python -m sage db
upgrade"; `db upgrade` applied the no-op label revision (row counts unchanged); the server then
booted and played.
