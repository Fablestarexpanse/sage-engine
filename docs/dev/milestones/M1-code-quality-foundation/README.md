# M1 — Code Quality Foundation

> **Historical record (marked 2026-09-13).** Kept as written for the reasoning trail; do not
> treat as current instructions. Superseded by: `docs/dev/STATUS.md` (M1 closed; phases 02-03 were never written as files) and `docs/dev/milestones/M2-sage-decoupling/`.

**Goal:** Establish a green CI baseline and add test coverage for the core
pure-logic modules that currently have zero tests (parser, command registry,
config loading, session state machine).

**Status:** completed — exit criteria exceeded (150 server tests, ruff/compileall clean; parser, config, and session suites all landed during the 2026-07/09 code-health cycles)

**Depends on:** none (green ruff baseline landed in the bootstrap commit)

**Exit criteria:**
- `python -m ruff format --check src tests` exits 0
- `python -m compileall -q src tests` exits 0
- `python -m ruff check src tests` exits 0
- `python -m pytest` exits 0 with ≥ 30 tests (up from 13)
- `tests/test_parser.py` covers `tokenize()`, `CommandRegistry`, and
  `CommandDispatcher`
- `tests/test_config.py` covers `load_config()`, `resolve_project_root()`,
  and `resolve_config_asset_path()`
- `tests/test_session.py` covers `Session` state transitions and
  `SessionManager` lifecycle

## Architecture references

- `docs/architecture.md#layer-2--game-engine` — command pipeline
- `docs/architecture.md#layer-1--network--protocol` — session state machine
- `docs/architecture.md#layer-3--state--data` — config loading

## Phases

| #  | Phase                                                                                 | Status |
|----|---------------------------------------------------------------------------------------|--------|
| 01 | Parser + registry tests ([phase-01-parser-registry-tests.md](phase-01-parser-registry-tests.md)) | done |
| 02 | Config loading tests ([phase-02-config-tests.md](phase-02-config-tests.md))           | todo   |
| 03 | Session state machine tests ([phase-03-session-tests.md](phase-03-session-tests.md)) | todo   |

## Notes

Green ruff baseline (37 files reformatted, 4 imports fixed) landed in the
bootstrap commit (`af16372`) before any phase was dispatched. The executor
receives a clean tree; format + lint + build gates pass from turn 0.

Broad `except Exception` catches throughout `src/` are intentional at system
boundaries (LLM calls, ComfyUI HTTP, WebSocket notification failures, YAML
file scanning) — they are not a target of this milestone. The pattern is
correct: catch broadly at the external-service boundary, log, and fall back
gracefully.

The command handlers in `commands/` (combat, items, movement, proficiency)
are deeply coupled to live Redis/Postgres state and are not covered by this
milestone. Integration tests for those require a running stack and are
deferred to a later milestone.
