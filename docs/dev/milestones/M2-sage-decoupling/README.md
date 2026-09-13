# M2 — SAGE engine decoupling

**Goal:** Turn the Fablestar codebase into a world-agnostic engine (SAGE) with Fablestar Expanse
as the first world package, proven by a second, deliberately different world running on
unchanged engine code.

**Status:** planning — Phase 1 contracts awaiting owner review

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
| 1 | Contracts | **awaiting owner review** |
| 2 | Scaffolding (proposed split 2a CI + ratchet, 2b move/rename, 2c seams + loader + skeleton world 2) | blocked on 1 |
| 3 | Migrate Fablestar system by system | blocked on 2 |
| 4 | Second reference world, full size | blocked on 3 |
| 5 | Tooling | blocked on 1 (decisions), 2 (format) |

## Notes

- Hard stop after stage 1 (brief §5). Do not dispatch executor phases before approval.
- Stage order changes are proposals in `PHASE1_CONTRACTS.md` §G until approved.
