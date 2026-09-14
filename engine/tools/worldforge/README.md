# WorldForge

Tauri desktop map editor for SAGE world zones — visual room graph with exits,
floors, stamps (reusable room groups), groups/notes, and editors for entities,
items, glyphs, ships, and the galaxy map. Writes YAML directly into
`content/world/`; the running server hot-reloads the changes.

See the root `CLAUDE.md` → "How WorldForge saves (and the conflict risk)"
before editing the same zone from more than one tool at once.

## Run

```bash
npm install
npm run tauri dev
```

`npm test` runs the vitest unit suite (utils + the Tauri IPC bridge contracts).
`npm run build` builds the web bundle; `npm run tauri build` packages the app.

The companion MCP server (`../worldforge-mcp/`) exposes the same map-building
operations as `mcp__worldforge__*` tools for LLM-driven zone drafting.
