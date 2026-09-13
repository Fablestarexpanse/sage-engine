# WorldForge Audit — 2026-09-11

> **Historical record (marked 2026-09-13).** Kept as written for the reasoning trail; do not
> treat as current instructions. Superseded by: `docs/dev/STATUS.md` (WorldForge done-list; criticals 7 and 8 are fixed in `worldforge/src-tauri/src/commands.rs`, `validate_zone` exists) and `docs/sage/PHASE0_AUDIT.md` §9.

Four-reviewer audit of the WorldForge Tauri app (`worldforge/`), its Rust bridge
(`worldforge/src-tauri/`), and the `worldforge-mcp/` tool surface. Read-only:
the working tree (including uncommitted WIP) was audited as-is.

Prior desloppify coverage: `worldforge-mcp/server.py` (exit-write dedupe,
atomic writes, docs) and package.json dep cleanup. The app itself had never
been audited before this.

## Critical (broken or active data loss)

1. **`create_room` MCP tool crashes** — `worldforge-mcp/server.py:842` calls
   `_warn_basement_floor()`, which is not defined anywhere; the intended helper
   `_validate_floor_for_slug` (line 546) exists but is never called. Every
   `mcp__worldforge__create_room` call raises NameError. Fix: wire the helper
   in (as a soft warning per the docstring's promise).
2. **Live-watch clobbers unsaved drafts** — App.jsx polls disk every 2 s;
   `useContentStore`'s soft-load replaces the whole entities/items/glyphs/
   systems/ships maps with new object references, and every secondary editor's
   draft-reset effect depends on that map — so the poll resets `draft` and
   `dirty=false` mid-typing. Affects EntityEditor, ItemEditor, GlyphEditor,
   GalaxyEditor, ShipEditor.
3. **Unsaved room edits silently discarded** — ZoneEditor `onNodeClick`
   (~2213) and the zone select (~1942) switch rooms/zones without consulting
   `panelDirty`; no beforeunload/close-request guard either. `panelDirty` only
   paints the badge.
4. **Optimistic UI before disk write, failures swallowed** — dispatch +
   success status fire before `fs.writeYaml` settles; `.catch(() => {})` at
   ZoneEditor 1009/1017/1036/1220, no catch at `saveRoomFile` (~1915), naked
   group save (~2678). A failed write leaves UI claiming success while disk is
   stale.
5. **MCP deletes `reference_image`** — `_read_positions`
   (worldforge-mcp/server.py:441-461) never carries `reference_image`, so any
   MCP positions round-trip (create/move/floor/layout/delete room) strips a
   human-set reference image from `.positions.json`.
6. **Nested `content/world/content/world/` bug reproducible** — the
   historical bug CLAUDE.md documents can recur: `createWorldScaffold`
   (worldScaffold.js:47-49) re-appends `content/world` onto the passed root
   instead of using the already-resolved `worldRoot`; picking an *empty*
   `content/world` folder triggers it.
7. **Rust `write_file` not atomic** — commands.rs:46-53 (and
   `write_binary_file` 113-120) truncate-write in place; the live server's
   HotReloader can observe torn/zero-length YAML. worldforge-mcp already does
   tempfile+rename; the Rust bridge should mirror it.
8. **No path confinement on Tauri fs commands** — read/write/delete/
   remove_dir_all take raw paths with no root check or `..` rejection
   (commands.rs:41-125), while `import_bundle` *does* guard traversal. CSP is
   `null`. Low urgency for a trusted desktop tool, real gap if webview content
   is ever attacker-influenced.

## High-value gaps (not crashes)

- **YAML-tab crash**: RoomPanel.jsx:1031 `yaml.load` un-caught — malformed
  YAML throws in the click handler.
- **`zone.yaml` shape split**: MCP writes `{id,name}` (only if display_name
  given, else no file); app scaffold writes `{name,type,status}`; neither
  satisfies `ZoneModel` (requires `description`). Standardize.
- **Validation asymmetry**: MCP hard-enforces direction-vs-position and
  same-floor up/down; the app checks neither (drag handles trust the handle).
  App's Validate panel checks entity/item/glyph references, dead ends,
  asymmetric exits; MCP has no `validate_zone` tool at all.
- **Dead `autoSaveNavigate` setting** — persisted, shown in Settings, never
  read. Tab switches unmount editors and lose drafts (App.jsx:453-475).
- **Stamps missing from Export/Import bundle** (ExportDialog.jsx:31-55).
- **Partial-failure orphans** — duplicateSelectedRooms / placeStampAtFlow
  write loops leave orphan files on mid-loop failure; undo entry pushed only
  after the loop.
- **`window.prompt` in Entity/Item/Glyph editors** instead of the app's own
  TextPromptModal; invalid ids silently no-op.
- **VALID_ROOM_TYPES dead** in MCP (defined, never used).
- Positions writes per keystroke/drag with swallowed errors, no debounce.
- ZoneEditor monolith (2714 lines): rebuildGraph alone ~320 lines with 18
  useCallback deps; audit lists 8 clean extraction seams (persistence, undo,
  room CRUD, connections+debug panel, layout tools, floors, stamps, input
  handling).
- UX: no redo, no delete-key, no bulk actions in multi-select, "TEMP: Clear
  all rooms" (no undo) lives in the always-visible toolbar.
- MCP capability gaps for the draft→polish loop: no stamps, no notes tool,
  no validate_zone.
- YAML dump style differs across writers (js-yaml force-double-quotes vs
  PyYAML defaults) → diff churn; js-yaml also deletes hand-written comments.
- Light theme palette diverges from admin-ui and omits `*Bg` tint tokens.

## Recommended order of attack

1. Fix `create_room` NameError + `reference_image` preservation (two small
   worldforge-mcp edits — restores the MCP surface and stops metadata loss).
2. Draft-loss trio in the app: live-watch clobber (effect deps), dirty guard
   on room/zone/tab switch + close, write-before-dispatch with visible errors.
3. Scaffold root fix + atomic Rust writes (the two disk-integrity items).
4. `zone.yaml` shape standardization + `validate_zone` MCP tool + port the
   two MCP geometry checks into the app's Validate panel.
5. Polish batch: TextPromptModal swaps, stamps in Export, partial-failure
   rollback, keyboard shortcuts/redo, demote the TEMP clear-all button.
6. Later: ZoneEditor decomposition along the 8 seams; path confinement + CSP
   in the Rust bridge.

Note: `worldforge/src` currently carries uncommitted user WIP — fixes touching
those files should coordinate with that work rather than land blind.


## Status update — 2026-09-11 (same day)

Fixed in commits `3419b3b`, `29a0d44`, `44c105f`:
- MCP `create_room` crash and `reference_image` loss (criticals 1 and 5)
- Nested `content/world/content/world` scaffold recurrence (critical 6)
- Live-watch draft clobber in all five secondary editors (critical 2)
- `window.prompt` → TextPromptModal, stamps in Export, import via `loadAll`
- Vitest infrastructure + 27 tests (utils, stamp bundle, Tauri IPC bridge)
- Theme tint-token parity, validation typedefs, dead export, shared deepClone

Still open — deferred as one batch blocked on the in-progress editor WIP
(criticals 3, 4, 7, 8 and the ZoneEditor decomposition): dirty-switch guards,
write-before-dispatch with visible errors, atomic Rust writes, path
confinement, mtime guard, TEMP delete-all retirement. Tracked as 31 skipped
issues in `worldforge/.desloppify/` with the reason attested.
