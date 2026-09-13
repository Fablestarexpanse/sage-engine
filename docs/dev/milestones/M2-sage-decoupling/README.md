# M2 — SAGE engine decoupling

**Goal:** Turn the Fablestar codebase into a world-agnostic engine (SAGE) with Fablestar Expanse
as the first world package, proven by a second, deliberately different world running on
unchanged engine code.

**Status:** in-progress — Phase 1 contracts approved 2026-09-13; stage 2a starting

**Depends on:** M1 (done)

**Exit criteria:** the brief's Definition of Done (`docs/sage/BRIEF.md` §9):
- `engine/` contains no Fablestar references, enforced by CI.
- Fablestar Expanse runs as a world package, feature-complete against today's build.
- The second reference world runs on the same engine with zero engine code changes.
- Switching worlds is a config change plus a restart.
- Login banner, MOTD, currency names, stat names and all player-facing vocabulary are editable
  from Nexus without touching code.
- AI prompts and style are world assets, versioned with rollback.
- A plugin installs and uninstalls cleanly, including its schema.
- No `.md` file still describes the engine as Fablestar-only; historical docs are marked.

## Architecture references

- `docs/sage/BRIEF.md` — owner brief (locked decisions, invariants)
- `docs/sage/DECISIONS.md` — rulings log
- `docs/sage/PHASE0_AUDIT.md` — inventory of everything world-specific
- `docs/sage/PHASE1_CONTRACTS.md` — world package contract, plugin API spec, §4 answers

## Stages

The brief's stages are not executor phases. Executor phase docs (`phase-NN-<slug>.md`) are
written on demand, only after the Phase 1 contracts are approved.

| Stage | Scope | Status |
|---|---|---|
| −1 | Stabilize: floors data loss, silent tick errors, stale commands on reload, regression guards | done (`sage/phase-0-1`) |
| 0 | Audit | done (`docs/sage/PHASE0_AUDIT.md`) |
| 1 | Contracts | done — approved 2026-09-13 |
| 2a | CI and ratchets | in progress — executor phases below |
| 2b | Mechanical move and rename to `engine/`, package `sage` | todo |
| 2c | Seams, plugin loader, lexicon, skeleton second world | todo |
| 3 | Migrate Fablestar system by system | blocked on 2 |
| 4 | Second reference world, full size | blocked on 3 |
| 5 | Tooling | decisions made (D.E); work after 2c |

## Phases (stage 2a)

Expanded on demand; later stages get phase docs when 2a lands.

| #  | Phase | Status |
|----|-------|--------|
| 01 | CI baseline — gates + WorldForge vitest in GitHub Actions ([phase-01-ci-baseline.md](phase-01-ci-baseline.md)) | done — first CI run green |
| 02 | Live test tier — `live` marker, Postgres/Redis CI job, migration up/down + persistence tests ([phase-02-live-test-tier.md](phase-02-live-test-tier.md)) | done — CI live job green |
| 03 | Invariant ratchet — denylist + player-string scanner with per-file baseline | todo (doc not yet written) |
| 04 | License report — clean-venv Python and npm/cargo license listing in CI | todo (doc not yet written) |

## Notes

- Stage 1 approved 2026-09-13; the revised stage order in `PHASE1_CONTRACTS.md` D.G is the plan.
- Owner amendments at approval are in `PHASE1_CONTRACTS.md` Part H.
