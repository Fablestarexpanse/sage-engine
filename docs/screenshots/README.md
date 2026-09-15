# Screenshots referenced by the root README

| File | What it shows |
|---|---|
| `player-client-fablestar.png` | Player client on the Fablestar Expanse server (dev login as Dev Tester, after `look`), light theme. |
| `player-client-rivermoot.png` | The same client on the Rivermoot server: world mark, accent, currency, level panel, map. Light theme. |
| `admin-content-items.png` | Admin console, Content Library > Items with `pulse_pistol` open: YAML editor, "used by" panel, item table with plugin columns. Light theme. |
| `admin-room-detail.png` | Admin console, Content Library > Rooms with `test_isle:town_plaza` open, and the rooms that link to it. Light theme. |
| `admin-world-plugins.png` | Admin console, World & plugins scrolled to the plugin table. Light theme. |
| `worldforge-zone-editor.png` | WorldForge with Rivermoot's `town` zone auto-laid-out and the Market Square's Plugins tab open. |

All captures are 1600x1000, taken with headless Chrome over the DevTools protocol against local dev
servers (Nexus on 8001 for Fablestar and 8002 for Rivermoot, the Vite clients on 5173, 5174 and
5175), using the passwordless dev logins. The player and admin captures of 2026-09-15 set each
client's light theme in local storage first. WorldForge (2026-09-14) ran as its Vite web build with
a read-only stand-in for the Tauri file commands, so nothing was written to disk. Re-capture after
visible UI changes, at the same size.
