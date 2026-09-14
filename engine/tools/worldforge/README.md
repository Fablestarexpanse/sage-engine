# WorldForge

Tauri desktop editor for SAGE world packages — visual room graph with exits,
floors, stamps (reusable room groups), groups/notes, and editors for entities and
items. Room types, exit directions and equipment slots come from the open world, and
plugin fields (shops, lodging, hazards, searchable features, item slots...) get forms
generated from the package's `content.schema.json`. Writes YAML directly into the
world's `content/world/`; the running server hot-reloads the changes.

See `docs/architecture.md` → "How WorldForge saves (and the conflict risk)"
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
