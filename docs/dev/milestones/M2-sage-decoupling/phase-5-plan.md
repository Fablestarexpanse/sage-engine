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
| 5.2 | One validator. `sage validate [--world]` runs `sage.world.lint`, and worldforge-mcp's `validate_zone` and room types come from the world package. The MCP instructions lose the sci-fi examples. | done |
| 5.3 | Content schemas. `sage schema export` and `GET /schema/world` give JSON Schema for rooms, features, entities and items (with every enabled plugin's extension fields) plus the world's lists (room types, exit directions, slots, attributes, currencies). | done |
| 5.4 | WorldForge reads the world. Room types, exit directions and equipment slots come from the package's `world.toml`. | done |
| 5.5 | WorldForge edits plugin content: room, feature and item forms for extension fields, generated from the exported schema. | done |
| 5.6 | Credit bundles are deployment config (`comfyui.toml`), served to the admin console. | done |
| 5.7 | World theme: `ui/theme.yaml` (accent colours, title glyph) served with `GET /play/world`, applied by player-ui. | todo |
| 5.8 | Nexus write-through for WorldForge: decide (build or defer) and record. | todo |

## Notes
- **5.1 server-sent command list (done).** `GET /play/commands` returns the registry's primary
  command names (`CommandRegistry.names()`). The player UI's `WorldContext` loads the list, and
  `CommandInput` autocompletes from it; the hardcoded 50-name list is gone.
  Run: live Fablestar lists 49 commands (including `prof`, `cap`, `factions`, `achievements`) and
  live Rivermoot 37 (including `level`, `rent`, `browse`; no `prof`/`cap`). In the browser (dev
  login), typing `pr` in the command box suggested `prof` from the server list.
- **5.2 one validator (done).**
  - **`sage.world.lint`:** now carries worldforge-mcp's zone checks at three levels:
    - warnings: missing room and feature descriptions, rooms with no exits or cut off from their zone, low feature density
    - info: one-way and cross-zone exits, dead ends, depth jumps, density
    - errors: self-referencing exits
    - With `zone=`, room findings cover that zone only; `lint_content()` works on a bare `content/world` directory.
  - **CLI:** `python -m sage validate [--world] [--zone] [--info]` prints the report and exits 1 on errors.
  - **worldforge-mcp:**
    - `validate_zone` calls `lint_content`, with room types and exit directions from the `world.toml` next to the content root.
    - The unused copy of Fablestar's twelve room types is gone. `create_room`/`update_room` refuse types the world does not declare, and `create_room` defaults to the first declared type.
    - `get_layout_guide` lists the room types. Space-station examples are now town, dock and castle examples.
  - **WorldForge:** its JS validator stays for now (D.E).
  - **Map fix found by the new connectivity check:** Rivermoot's riverside was two halves joined only through town. Eel weirs south now meets mudflats north, wading the shallows.
  - **Run:**
    - `sage validate --world rivermoot` gives 0 errors, 0 warnings, exit 0.
    - `--world fablestar` gives the 3 dangling owner exits and a zero-density `aipub`, exit 1.
    - Called the MCP functions on a Rivermoot copy (`test_worldforge_mcp.py`); the MCP process already running in this session still has the old code, so its tool was not called.
- **5.3 content schemas (done).**
  - **`sage.world.schema.content_schema(world, extensions)`** collects:
    - the world's id and name
    - `content` lists (room types, exit directions, equipment slots)
    - attributes, vitals and currencies
    - JSON Schema for room, feature, entity, item and zone
    - every enabled plugin's extension fields, with owners
  - **How to get it:**
    - Staff: `GET /schema/world`.
    - Without a server: `python -m sage schema export [--world] [--out]`. This uses `sage.plugins.offline.registration_host`, which runs plugin setup with no database, Redis or HTTP and reads only what the plugins register.
  - **Offline copies:** each world package commits one at `content.schema.json`, and `test_exported_schema_is_current` fails with the regenerate command when it goes stale.
  - **Run:** the live `/schema/world` on both servers matched the exported files exactly (401 without a token).
- **5.4 WorldForge reads the world (done).**
  - **Loading:** WorldForge loads the package's `content.schema.json` (beside `world.toml`, two levels above `content/world`) with the content (`state.worldSchema`). `utils/worldSchema.js` turns it into lists.
  - **What follows the world:**
    - The room panel offers the world's room types. A room with an undeclared type still shows it.
    - "Add exit" offers only the world's directions.
    - New rooms use the default room type if the world allows it, else the world's first type.
    - The zone validator errors on undeclared room types and exit directions.
  - **A folder that is not a package:** falls back to the room types its content already uses and every direction. That replaces Fablestar's hardcoded twelve types.
  - **Removed:** `utils/itemValidation.js`. Nothing imported it, and it checked Fablestar-era fields no engine code reads (`equip_slot`, `weapon_profile`, `on_use`).
  - **Run:**
    - vitest 40 passed, and the app builds.
    - Loading the real packages with Node gave Rivermoot 13 room types, north/south/east/west and hand/body; a "chamber" default becomes "street".
    - Fablestar keeps its twelve types and ten directions.
    - The Tauri app itself was not launched: its file access needs the Tauri runtime.
- **5.5 WorldForge edits plugin content (done).**
  - **`components/ExtensionBlocks.jsx`:** renders a form for each plugin field a content kind carries in this world, read from `content.schema.json`.
    - Handles objects, `$defs` references, lists of values or objects, maps, numbers, booleans, strings and enums.
    - Each block has Add (seeded with schema defaults) and Remove.
  - **Where it appears:**
    - Rooms: a Plugins tab (shop, lodging, ambient, hazards). It replaces the hand-built Hazards tab.
    - Features: an inline form under each feature (search).
    - Items: a "Plugin fields" section. `slot` is a select of the world's equipment slots.
  - **A folder without a schema:** the form says to use the YAML tab.
  - **Run:** vitest 45 passed. The new tests render the forms from Rivermoot's real exported schema and check helper defaults and `$ref` resolution. The app builds.
  - **Not launched:** the Tauri app itself.
- **5.6 credit bundles are deployment config (done).**
  - **Config:** `ComfyUIConfig.credit_bundles` reads `[[credit_bundles]]` entries (`id`, `label`, `credits`, `blurb`). The default is none. The comfyui settings save writes the bundles back.
  - **Admin console:** `GET /admin/economy` (players tool) serves the bundles with the credit rate and currency name. The Players & accounts editor shows them, or says none are configured. It no longer has its own dollar table or the hardcoded "100 px ≈ $1".
  - **Example file:** `config/comfyui.example.toml` carries the four bundles the console used to hardcode.
  - **Local dev config:** I appended the same four bundles to `config/comfyui.toml` so this machine's console is unchanged. The file is gitignored; a backup is in the scratchpad.
  - **Run:**
    - Live `/admin/economy` returns the four bundles, "pixels" and 100 (401 without a token).
    - `test_credit_bundles.py` loads bundles from TOML, survives an admin save, and checks the route.
    - The admin screen was not opened: signing in needs a password.

