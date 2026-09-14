# engine/ — SAGE (Synthetic Agent Game Engine)

This directory is the home of the SAGE engine and holds its license, [`LICENSE`](LICENSE)
(`FSL-1.1-ALv2`). Plain-English summary: [`../LICENSE-FAQ.md`](../LICENSE-FAQ.md). Scope of the
license: [`../NOTICE`](../NOTICE).

Layout:

- `src/sage/` — the engine package (`python -m sage`)
- `tests/` — hermetic and live tests; run from the repository root with `python -m pytest`
- `alembic/`, `alembic.ini` — core migrations (`python -m sage db upgrade`)
- `scripts/` — admin bootstrap and account scripts
- `pyproject.toml`, `requirements.lock` — packaging (`pip install -e "./engine[dev]"`)
- `clients/admin-ui`, `clients/player-ui` — Nexus console and player client (Vite)
- `tools/worldforge` (Tauri world editor), `tools/worldforge-mcp` (MCP map tools)

The engine runs one world package from `<repo>/worlds/<id>` (set `world` in `config/server.toml`),
loads first-party plugins from `<repo>/plugins`, and reads deployment config from `<repo>/config`,
so start it from the repository root.
