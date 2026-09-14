# Phase 05: World packages and the running world

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** stage 2b
**Estimated diff:** ~450 lines
**Tags:** language=python, kind=feature, size=m

## Goal

First stage-2c seam (contracts Part B, D.G item 2c): the engine loads a world package and reads
every world-specific path and start/respawn room from it, instead of hardcoded `content/`,
`prompts/` and `test_isle:*` literals. Fablestar becomes `worlds/fablestar/` with its content
still at the repo root via a transitional manifest pointer.

## Spec (as built)

1. `engine/src/sage/world/package.py` — `WorldManifest` (world id/name/version/engine range/
   locale, start room + respawn, content lists, plugins, params, `[transition]` dirs),
   `StatSchema`, `Currency`, `WorldPackage` (paths: `content_dir`, `prompts_dir`, `lexicon_dir`,
   `zones_dir`), `load_world_package` (validates id vs directory, engine range vs
   `sage.ENGINE_VERSION`, content dir exists), `available_worlds` (ignores `_`-prefixed),
   `select_world` (configured world, else the only one, else a clear error).
2. `ServerConfig.world` / `worlds_dir`; `SageServer.world` selected at construction (fails fast).
3. Replaced literals: `ContentLoader`, `PromptManager`, hot-reload watch/invalidate, zone map,
   respawn and missing-room start in `_bootstrap_session`, agents respawn, character creation,
   admin content/agents/shops/play routes, scene art output, `content_browser.set_content_root`.
   `sage/world/defaults.py` (the `test_isle` constants) deleted.
4. `worlds/fablestar/{world.toml,stats.yaml,currencies.yaml}`.
5. Tests: `engine/tests/test_world_package.py` (10); fakes get `repo_world()`.

## Update Log

### Update — 2026-09-13 (complete)

Executed by the architect directly. Gates clean; 392 passed + 5 skipped; ratchet 2188 → 2187
(the galaxy/system/ship/glyph browser paths are deliberately not re-pointed — slated for
deletion). Real run: `python -m sage` logs `World: fablestar (Fablestar Expanse 0.1.0) from
…/worlds/fablestar`; a dev-login player sees Ferry Landing, `say` works, `quit` says Goodbye.
