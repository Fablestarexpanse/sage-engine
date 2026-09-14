# Phase 5 plan: tooling

**Milestone:** M2 — SAGE engine decoupling · **Branch:** `sage/phase-5` (stacked on `sage/phase-4`) · **Status:** in progress

Living plan. The tool surface was decided as a set at the Phase 1 review (`PHASE1_CONTRACTS.md`
D.E, owner G.1/G.6). Phase 3 already retired the admin World Builder (3.18a) and the
galaxy/ship/glyph editors (3.18). Phase 5 does the rest of D.E. The rules are unchanged: both
worlds stay playable at every commit, the ratchet only goes down, a real run goes in every commit
message, and the full suite runs before each commit.

## Read-through (2026-09-14)

- **player-ui autocomplete:** a hardcoded list of about 50 command names that "mirrors the server's registry". It offers Fablestar's `cap`/`prof`/`bonus` in Rivermoot and none of a new world's commands (audit D.F 2).
- **Validation:** worldforge-mcp keeps its own `validate_zone` and a `VALID_ROOM_TYPES` set copied from Fablestar. Its instructions use space-station examples. Phase 4 added `sage.world.lint`, but nothing outside tests uses it.
- **Schemas:** the engine exposes no JSON Schema for content. Only `ContentExtensions.schemas()` exists, and nothing serves it.
- **WorldForge:** hardcodes Fablestar's twelve room types in `RoomPanel.jsx` and does not read `world.toml`. No tool edits the plugin content blocks (`shop`, `lodging`, `ambient`, `hazards`, feature `search`, item `slot`/`heal`/...).
- **Admin console:** credit bundles (`$4.99 → 500` ...) are constants in `PlayerAccountsTab.jsx`, though D.E says deployment config.
- **Player UI theme:** one built-in theme for every world; `ui/theme.yaml` from D.E does not exist.
- **Nexus write-through for WorldForge:** D.E planned it on the `/content/*` room routes with `expected_mtime`. 3.18a deleted those routes with the World Builder, their only caller.

## Steps

| # | Step | Status |
|---|------|--------|
| 5.1 | The server sends the command list: the player client autocompletes the running world's commands (engine + enabled plugins), not a hardcoded list. | done |
| 5.2 | One validator. `sage validate [--world]` runs `sage.world.lint`, and worldforge-mcp's `validate_zone` and room types come from the world package. The MCP instructions lose the sci-fi examples. | todo |
| 5.3 | Content schemas. `sage schema export` and `GET /schema/world` give JSON Schema for rooms, features, entities and items (with every enabled plugin's extension fields) plus the world's lists (room types, exit directions, slots, attributes, currencies). | todo |
| 5.4 | WorldForge reads the world. Room types, exit directions and equipment slots come from the package's `world.toml`. | todo |
| 5.5 | WorldForge edits plugin content: room, feature and item forms for extension fields, generated from the exported schema. | todo |
| 5.6 | Credit bundles are deployment config (`comfyui.toml`), served to the admin console. | todo |
| 5.7 | World theme: `ui/theme.yaml` (accent colours, title glyph) served with `GET /play/world`, applied by player-ui. | todo |
| 5.8 | Nexus write-through for WorldForge: decide (build or defer) and record. | todo |

## Notes
- **5.1 server-sent command list (done).** `GET /play/commands` returns the registry's primary
  command names (`CommandRegistry.names()`). The player UI's `WorldContext` loads the list, and
  `CommandInput` autocompletes from it; the hardcoded 50-name list is gone.
  Run: live Fablestar lists 49 commands (including `prof`, `cap`, `factions`, `achievements`) and
  live Rivermoot 37 (including `level`, `rent`, `browse`; no `prof`/`cap`). In the browser (dev
  login), typing `pr` in the command box suggested `prof` from the server list.

