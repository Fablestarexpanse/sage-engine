# engine/ — SAGE (Synthetic Agent Game Engine)

This directory is the home of the SAGE engine and holds its license, [`LICENSE`](LICENSE)
(`FSL-1.1-ALv2`). Plain-English summary: [`../LICENSE-FAQ.md`](../LICENSE-FAQ.md). Scope of the
license: [`../NOTICE`](../NOTICE).

Layout (stage 2b of `docs/sage/PHASE1_CONTRACTS.md` Part A):

- `src/sage/` — the engine package (`python -m sage`)
- `tests/` — engine tests; run from the repository root with `python -m pytest`
- `alembic/`, `alembic.ini` — core migrations (`python -m sage db upgrade`)
- `scripts/` — admin bootstrap scripts
- `pyproject.toml`, `requirements.lock` — packaging (`pip install -e "./engine[dev]"`)
- `clients/admin-ui`, `clients/player-ui` — Nexus console and player client (Vite)
- `tools/worldforge` (Tauri world editor), `tools/worldforge-mcp` (MCP map tools)

During the transition the engine still reads world content from `<repo>/content`,
deployment config from `<repo>/config` and prompts from `<repo>/prompts`, so run it from the
repository root. 