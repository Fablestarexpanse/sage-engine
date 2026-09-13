# Phase 09: Second reference world and per-world smoke test

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** phase-08
**Tags:** language=python+yaml, kind=feature, size=m

## Goal

Brief §6 and contracts D.G item 3: a deliberately different world exists from stage 2c on, so
every seam Phase 3 cuts is exercised by two worlds. Brief invariant 5: both reference worlds
boot and play in CI.

## Spec (as built)

1. `worlds/rivermoot/` — low-fantasy river town (owner G.9: SAGE has no genre; this is a
   harness). Three rooms (`town:bridge` start, `town:market`, `town:shrine` respawn), a river
   rat, attributes `mgt`/`wts`/`nrv` (Might/Wits/Nerve), currency `silver`, its own lexicon
   (login banner, MOTD, who, death lines, stat labels), no agents, no AI images.
2. `worlds/rivermoot/plugins/levels/` — world-private plugin: `EntityKilled` → experience
   (`levels.xp_per_kill`, `levels.xp_per_level` params), level-ups as kill lines, `level`/`lvl`
   command reading its `levels` state block, `levels.*` lexicon.
3. `engine/tests/test_world_rivermoot.py` — loads the world and plugin through the real host:
   world differs from Fablestar, lexicon overrides, XP and level-up, `level` command.
4. `engine/tests/live/test_world_smoke.py` — for every world in `worlds/`, start
   `python -m sage` with `SAGE_SERVER__WORLD=<id>` on the live tier's throwaway database,
   dev-login, and play: start room, `say`, walk the first exit and back, `who`, `quit`; assert
   no unresolved lexicon keys and no tracebacks. Waits for the prompt, not idle timeouts.
5. With two worlds, `server.world` is required; `config/server.example.toml` sets it.

## Update Log

### Update — 2026-09-13 (complete)

426 passed + 7 skipped; live tier 7 passed, six consecutive local runs clean (an earlier
idle-timeout version of the driver was flaky on Fablestar's slower first replies). Rivermoot
transcript: banner "~ Rivermoot ~ …", MOTD, Old Bridge → Market Square → Old Bridge, `who`,
Goodbye — on the unchanged engine. Known non-real seams (Phase 3): new Rivermoot characters
still get Fablestar's default stat blob and the built-in proficiency catalog.
