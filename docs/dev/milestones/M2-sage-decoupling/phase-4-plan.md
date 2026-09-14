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
| 4.2 | Attribute point-buy at character creation. The engine's default chargen slots offer `kind: "attribute_points"` when `stats.yaml` sets `attribute_points`, and player-ui renders it. | done |
| 4.3 | Levels that matter. The `levels` plugin provides `combat.ratings` from Might/Nerve plus level, and a level raises maximum health. | done |
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
- **4.2 attribute point-buy (done).** `define_engine_slots(resolvers, world)` gives a world whose
  `stats.yaml` sets `chargen.attribute_points` engine chargen slots (`attribute_point_buy`), so no
  plugin is needed. `attribute_points` is the most all attributes may add up to; each attribute
  stays in its min..max, and any left out keep their default. That matches Fablestar's design
  target (five attributes, 65 points), although Conduit keeps providing its own `skill_points`
  choices there. player-ui renders the new kind with `ChargenAttributesStep` and sends
  `{"attributes": {...}}`. Run: live Rivermoot options list Might/Wits/Nerve, budget 8; the API
  refused 5+2+2 (`attribute_budget_exceeded`) and Might 0 (`attribute_out_of_range:mgt`) and
  created "Point Buyer" with 4/1/3. The creation screen itself was not driven in a browser (it
  needs a password sign-in).
- **4.3 levels that matter (done).** `levels` provides `combat.ratings` (attack = Might + level/2,
  defense = Nerve/2 + level/3) and `progression.total_levels`. Each level adds
  `levels.hp_per_level` (2) maximum health and heals that much. The run found a seam: a kill
  published inside combat's `state.edit` could not raise `max_hp`, because the ownership check
  only allowed keys declared by the editing plugin. The level-up aborted the whole save with
  "plugin combat changed stats it does not own", so the kill's experience and counters were
  lost. Engine-owned keys are now writable when any loaded plugin declares them in `stats_keys`.
  Run (live Rivermoot): the first rat took 3 damage (attack 2 + d6 1, below the old flat
  default's minimum of 4); after the fix the second kill printed the level-up and stored level 2,
  `hp = max_hp = 14`.

