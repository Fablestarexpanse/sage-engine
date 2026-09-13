# Phase 06: Lexicon service

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** phase-05
**Tags:** language=python, kind=feature, size=m

## Goal

Brief locked decision 7 and invariant 3: player-facing strings are world-supplied lexicon keys.
This phase builds the resolution service, adds `Session.say(key, **vars)`, delivers the login
banner and MOTD (new), and converts the first slice of engine strings. Nexus live editing
(`world_overrides` rows) is a later phase; the override layer already exists in the API.

## Spec (as built)

1. `sage.lexicon`: `Lexicon` (ordered layers), `build_lexicon(world_lexicon_dir, locale,
   overrides=, plugin_layers=)`, `set_active`/`active`/`t`. Order: override → world → plugins →
   engine defaults (`sage/lexicon/en.yaml`, packaged) → `[key]`. `{name}` placeholders; missing
   variables stay visible; malformed templates return unformatted.
2. `Session.say`; prompt line from `prompt`.
3. Converted: prompt, rate limit, command error, unknown command + suggestions, help header /
   unknown / no description (plus `help.<verb>` over docstrings), who empty/header, death wake +
   bill lines, new-player hint. Login banner and MOTD sent after bootstrap when non-empty.
4. `worlds/fablestar/lexicon/en.yaml` carries the Fablestar wording ("The station is silent.",
   the clinic wake-up) that was hardcoded in the engine.
5. Lexicon files hot-reload. Invariant scanner now also scans YAML.

## Update Log

### Update — 2026-09-13 (complete)

Gates clean; 399 passed + 5 skipped (7 lexicon tests, including "every key the engine uses
has an engine default"). Ratchet player literals 177 → 169; YAML scanning added no hits.
Real run on the Fablestar world: unknown command and suggestion lines, `help say`, `who` list
all render through the lexicon; appending a MOTD to `worlds/fablestar/lexicon/en.yaml` while
the server ran made the next login show it (reverted afterwards).
