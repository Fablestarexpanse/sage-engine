# Phase 4 plan: Rivermoot at full size

**Milestone:** M2 — SAGE engine decoupling · **Branch:** `sage/phase-4` (stacked on `sage/phase-3`) · **Status:** in progress

Living plan. The brief (section 6) asks for a second world, deliberately unlike Fablestar, of
20–40 rooms. It has three attributes, one currency, no glyphs, a different genre and a different
progression model. It is "the test harness for the abstraction. Any seam it can't flex is a seam
that isn't real yet." Rivermoot has been a three-room skeleton since stage 2c. Phase 4 grows it,
and each step fixes, in the engine, whichever seam the bigger world shows is still shaped like
Fablestar.

Rules carried from Phase 3: the game stays playable in both worlds at every commit, ratchet
counts only go down, each commit message records a real run, and every owner-facing choice goes
into `docs/sage/DECISIONS.md`.

## Seams found before starting (2026-09-14 read-through)

- `stats.yaml` is loaded and never applied. New characters get `strength`/`dexterity`/
  `intelligence`/`perception` from `state.models.default_character_stats`. `max_hp` defaults to
  100 at login and to 20 in the death resolver, whatever the world's vitals say (Rivermoot: 12).
- The engine's default `combat.ratings` reads `strength`/`dexterity`, which no world declares.
- `stats.yaml` `chargen.attribute_points` is parsed and never used. The player client can only
  render Conduit's `skill_points` choices.
- The `levels` plugin gives experience and nothing else: no effect on combat or health.

## Steps

| # | Step | Status |
|---|------|--------|
| 4.1 | The stat schema is real. New characters get the world's attributes and vitals, login and death use the world's vital maximum, the engine's default ratings no longer read D&D keys, and `default_character_stats` is empty. | done |
| 4.2 | Attribute point-buy at character creation. The engine's default chargen slots offer `kind: "attribute_points"` when `stats.yaml` sets `attribute_points`, and player-ui renders it. | todo |
| 4.3 | Levels that matter. The `levels` plugin provides `combat.ratings` from Might/Nerve plus level, and a level raises maximum health. | todo |
| 4.4 | The map. 20–40 rooms over three zones (town, docks and riverbank, the old mill and marsh), entities and items, north/south/east/west exits only. | todo |
| 4.5 | First-party plugins in a second world. Rivermoot enables equipment (hand/body), consumables, shop and lodging (priced in silver), search, effects (rest) and ambient; fix whatever assumes Fablestar. | todo |
| 4.6 | Rivermoot's AI. Room narration with its own style, and no image slots (owner G.9: no AI images). | todo |
| 4.7 | Proof. The live smoke test plays a longer Rivermoot script (buy, equip, fight, level, rest, die and wake at the shrine). A real server runs on its own Rivermoot database (one database per world). | todo |

## Notes
- **4.1 stat schema (done).** At creation the engine seeds `stats.yaml` attribute defaults
  through `progression.seed_attributes`, then full vitals (`WorldPackage.seed_vitals`), then the
  chargen choices. Login backfills missing vitals from the world. The death resolver's fallback
  maximum is the world's (`vital_max`). The default `combat.ratings` is a flat (3, 2): which
  attributes make a fighter is the world's call. Conduit's `seed_attributes` matches keys
  case-insensitively, so Fablestar's lower-case `stats.yaml` reaches its upper-case block.
  Existing characters keep whatever top-level keys they have.
  Run: a new Rivermoot character on its own database (`sage_rivermoot`, launch config
  `nexus-rivermoot`, port 8002) stores `mgt/wts/nrv = 2`, `hp = max_hp = 12`, 10 silver. Before
  this step it would have got `strength`/`dexterity`/`intelligence`/`perception` and 100 hp. A new
  Fablestar character stores Conduit attributes at 13 and 100 hp (probe deleted).

