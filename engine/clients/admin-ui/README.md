# SAGE Nexus Admin Console

React (Vite) admin console for a running SAGE world. Pages are grouped by staff job:

- **Overview**: dashboard.
- **Live**: who's online (players and agents), live world (who is in each room, every live
  creature, items on floors, spawn and clean-up), staff feed, broadcast and scheduled restart.
- **Players**: characters (sheet drawn from the world's plugin panels, move, money, items, restore,
  undo history), accounts (suspension, mute, sign-in history, AI art credits, console access, GM
  crown), player reports, moderation (registration lock, sign-in address recording, address bans).
- **World**: world and plugins, Content Library (rooms, and searchable, sortable item and creature
  tables with plugin columns and a "used by" panel), skills catalog, lexicon and MOTD, AI Forge.
- **Economy**: money in circulation, shops, AI art credit prices.
- **NPCs**: agents. **System**: server and AI models, team and access (role presets), audit log.

Plugin pages (skills, shops, agents) appear only when the running world has those plugins. Ctrl+K
searches everything, and every record has its own address (`#/characters/17`,
`#/content/items/<id>`). Rooms and zones are built in WorldForge; the console only reads them.

## Run

```bash
npm install
VITE_API_BASE=http://localhost:8001 VITE_WS_BASE=ws://localhost:8001 npm run dev -- --port 5174 --host
```

Requires the Nexus server on port 8001 (see the root README quick start). Staff sign in with Nexus
console credentials; with `dev_mode` and `dev_login` on, the sign-in page also offers a
passwordless head-admin login for loopback clients.

`npm run build` for production, `npm run lint` for ESLint.
