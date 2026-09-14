# SAGE Player Client

React (Vite) web client for any SAGE world — MUD terminal over WebSocket, panels the
world's plugins declare (character sheet, skills, gear, standings...), character creation
with the world's choices (attribute points or a skill picker), AI portraits and scene art,
and the scene gallery. Title, mark, accent colour, currency and command autocomplete come
from the server it connects to.

## Run

```bash
npm install
VITE_NEXUS_PORT=8001 npm run dev -- --port 5173 --host
```

Requires a Nexus server (port 8001 by default; `VITE_NEXUS_PORT` points it elsewhere, for example 8002
for a second world). See the root README quick start.

`npm run build` writes `dist/`, which Nexus serves at its own address (http://localhost:8001/); a
build talks to the origin it was loaded from. Set `VITE_NEXUS_URL` at build time to host the build
somewhere other than the Nexus it uses.
Login issues a play session token; the password is not re-sent per action.

Source conventions (named exports, `mud/` file numbering) are documented in
[src/CONVENTIONS.md](src/CONVENTIONS.md).
