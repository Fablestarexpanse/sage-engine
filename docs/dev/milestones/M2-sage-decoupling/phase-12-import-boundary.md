# Phase 12: Import-boundary check

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** phase-08
**Tags:** language=python, kind=feature, size=s

## Goal

Brief invariant 1 (contracts Part E): `engine/` never imports from `worlds/` or `plugins/`,
and plugins reach the engine only through `sage.api` — enforced mechanically in CI, with zero
tolerance rather than a ratchet.

## Spec (as built)

In `scripts/sage_invariants.py` (already a CI step):
1. Engine sources (`engine/src`): any import of `sage_plugins.*` / `sage_worlds.*` fails; any
   `importlib.import_module`, `importlib.util.spec_from_*`, `__import__` or `sys.path` mutation
   fails outside `sage/plugins/loader.py` and `sage/commands/registry.py`.
2. Plugin sources (`plugins/**`, `worlds/*/plugins/**`, excluding migrations): any `sage.*`
   import other than `sage.api` fails (`from sage import api` allowed).
3. Chosen over import-linter: no new dependency, and plugins are loaded by path so their module
   names (`sage_worlds.<w>.plugins.<id>`) aren't importable for a static contract tool anyway.

## Update Log

### Update — 2026-09-13 (complete)

4 new tests (engine forbidden imports, dynamic-import allowlist, plugin API-only rule, repository
clean). Real check: changing the Rivermoot levels plugin to import `sage.core.events` made
`check` exit 1 with "plugins may import only sage.api"; reverted → exit 0.
