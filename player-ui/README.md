# Fablestar Player Client

React (Vite) web client for playing Fablestar — MUD terminal over WebSocket,
character sheet, chargen with the Conduit proficiency picker, AI portraits and
scene art, and the scene gallery.

## Run

```bash
npm install
VITE_NEXUS_PORT=8001 npm run dev -- --port 5173 --host
```

Requires the Nexus server on port 8001 (see the root README quick start).
Login issues a play session token; the password is not re-sent per action.

Source conventions (named exports, `mud/` file numbering) are documented in
[src/CONVENTIONS.md](src/CONVENTIONS.md).
