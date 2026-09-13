# engine/ — SAGE (Synthetic Agent Game Engine)

This directory is the home of the SAGE engine and holds its license, [`LICENSE`](LICENSE)
(`FSL-1.1-ALv2`). Plain-English summary: [`../LICENSE-FAQ.md`](../LICENSE-FAQ.md). Scope of the
license: [`../NOTICE`](../NOTICE).

Layout (stage 2b of `docs/sage/PHASE1_CONTRACTS.md` Part A):

- `src/sage/` — the engine package (`python -m sage`)
- `tests/` — engine tests; run from the repository root with `python -m pytest`
- `alembic/`, `alembic.ini` — core migrations (`python -m alembic -c engine/alembic.ini upgrade head`)
- `scripts/` — admin bootstrap scripts
- `pyproject.toml`, `requirements.lock` — packaging (`pip install -e "./engine[dev]"`)

During the transition the engine still reads world content from `<repo>/content`,
deployment config from `<repo>/config` and prompts from `<repo>/prompts`, so run it from the
repository root. The React clients and WorldForge move under `engine/` in the next 2b step.
