# SAGE Nexus Admin Console

React (Vite) admin console for the Nexus server — dashboard, Content Library
(zones/rooms/entities/items), AI Forge, player-account moderation and credit grants, lexicon and
MOTD editing, plugin pages (skills catalog, agents, shops) that appear only when the running world
enables those plugins, staff roles, and live presence. Structural room editing is WorldForge's job.

## Run

```bash
npm install
VITE_API_BASE=http://localhost:8001 VITE_WS_BASE=ws://localhost:8001 npm run dev -- --port 5174 --host
```

Requires the Nexus server on port 8001 (see the root README quick start).
Staff log in with Nexus console credentials; in `dev_mode` the bootstrap
seeds a head-admin account.

`npm run build` for production, `npm run lint` for ESLint.
