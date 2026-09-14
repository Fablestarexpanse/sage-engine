# Changelog

## Release process — record the publish date

SAGE is licensed under `FSL-1.1-ALv2` (`engine/LICENSE`). Each version converts to the Apache
License 2.0 on the **second anniversary of the date that version is made available**, so every
release entry must record that date. The date is part of the licence terms, not bookkeeping.

For every tagged release:

1. Add a section headed `## [<version>] — published YYYY-MM-DD`, using the date the version is
   first made available to anyone outside the licensor (push of a public tag, package upload,
   or delivery to a customer, whichever comes first). A private internal tag is not publication.
2. Add the line `Apache-2.0 conversion date: YYYY-MM-DD` (publish date plus two years).
3. Tag the commit `v<version>` and use the same publish date in the tag message.
4. Never edit a recorded publish date after release.

Versions built before the first publication have no conversion date.

## [Unreleased]

- **SAGE decoupling complete** (merged 2026-09-14, PRs #7–#12; repository now
  `Fablestarexpanse/sage-engine`). The engine (`engine/src/sage`) runs world packages
  (`worlds/fablestar`, `worlds/rivermoot`) and first-party plugins (`plugins/`) through a sealed
  plugin API. Every Fablestar mechanic is now a plugin, player text goes through the lexicon, AI
  prompts, style and ComfyUI graphs belong to the world, and Redis keys are namespaced per world.
- **Rivermoot**, the second reference world: 30 rooms, three attributes, silver, levels, ten
  plugins, text-only AI; it boots and plays in CI on the same engine code as Fablestar.
- **Schema (one-way migrations):** character state is JSONB; wallet balances live in stats;
  `echo_credits` became `ai_credits`; `digi_balance`, `reputation` and the retired agent table
  are dropped. Run `python -m sage db upgrade` (core and plugin branches).
- **Tools:** `python -m sage validate` and `python -m sage schema export`; WorldForge reads the
  world's room types, directions and slots and edits plugin fields through generated forms;
  worldforge-mcp validates with the engine linter. The admin World Builder and the
  glyph/galaxy/ship/system surfaces were removed.
- **Clients:** world theme (`ui/theme.yaml`), server-sent command autocomplete, attribute
  point-buy at character creation, plugin admin pages shown only when enabled, credit bundles
  in `comfyui.toml`. Zones without editor layout draw their map from exits.
- Licensing: SAGE engine licensed under FSL-1.1-ALv2 (`engine/LICENSE`); Fablestar Expanse
  content declared proprietary (`NOTICE`). Replaces the undeclared MIT entry in
  `pyproject.toml`.
- SAGE decoupling Phase −1: admin World Builder saves no longer erase WorldForge floors; tick
  handler errors are logged; hot reload drops removed commands.

## [0.2.0] — not published

Pre-SAGE Fablestar MUD platform. Internal version only; never made available, so no conversion
date applies.
