# REXYMCP.md

> **SAGE decoupling complete (merged 2026-09-14).** For how the codebase is split (engine,
> world packages, plugins) read `README.md` and `CLAUDE.md`; the contracts and rulings are in
> `docs/sage/`.

The rexyMCP architect/executor workflow contract for the SAGE engine
project — whatever agent acts as the architect reads this first.

## Read these first

1. `docs/dev/STANDARDS.md` — engineering Definition of Done.
2. `docs/dev/WORKFLOW.md` — phase lifecycle, status transitions, Update
   Log templates.
3. `docs/dev/NEXT.md` — names the active phase.
4. `docs/architecture.md` — the design.

## Commands

| Command | Purpose |
|---|---|
| `python -m ruff format engine/src engine/tests` | Format (writing form; idempotent after the post-write hook) |
| `python -m compileall -q engine/src engine/tests` | Build (bytecode/syntax gate — Python has no compile step) |
| `python -m ruff check engine/src engine/tests` | Lint / static analysis |
| `python -m pytest` | Tests |

## Executor

Phases are executed by a **local LLM** reached through the rexyMCP MCP
server (`rexymcp serve`). The executor's contract is **embedded** in the
server binary — there is *no* root `AGENTS.md` or executor-contract file
in this repo.

To dispatch a phase: `/rexymcp:dispatch <phase>`. To review the result:
`/rexymcp:review <phase>`.
