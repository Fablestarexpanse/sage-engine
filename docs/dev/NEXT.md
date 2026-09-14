# NEXT

Active milestone: **M2 — SAGE engine decoupling** (`docs/dev/milestones/M2-sage-decoupling/`).

Active phase: **none — Phases 3 and 4 complete (2026-09-14), awaiting owner review.** Stages 2a, 2b and 2c
and Phase 3 are up as stacked PRs #7 → #8 → #9 → #10; Phase 4 (Rivermoot at full size) is on
`sage/phase-4`, stacked on Phase 3. Next: Phase 5, tooling. The live breadcrumb is the `NEXT:` line at the top of `docs/sage/DECISIONS.md`;
Phase 3 step notes are in `docs/dev/milestones/M2-sage-decoupling/phase-3-plan.md`.

Layout: `engine/src/sage` (server, `python -m sage`), `engine/tests` (`python -m pytest` from the
repo root), `engine/alembic`, `engine/clients/{admin-ui,player-ui}`,
`engine/tools/{worldforge,worldforge-mcp}`, first-party plugins in `plugins/`, world packages in
`worlds/{fablestar,rivermoot}` (content, lexicon, AI prompts/style/ComfyUI graphs, world plugins).

Phase 1 contracts were approved by the owner on 2026-09-13 (`docs/sage/PHASE1_CONTRACTS.md`,
amendments in Part H). Rulings log: `docs/sage/DECISIONS.md`. Stage 2a (CI and ratchets) is done;
stages 2b and 2c get phase docs next.

Pre-SAGE status and backlog: `docs/dev/STATUS.md`.
