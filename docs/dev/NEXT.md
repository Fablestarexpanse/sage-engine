# NEXT

Active milestone: **M2 — SAGE engine decoupling** (`docs/dev/milestones/M2-sage-decoupling/`).

Active phase: **none — M2 is complete.** Every brief phase (−1 through 5) landed and was merged into
`main` on 2026-09-14 (PRs #7–#12); the repository moved to `Fablestarexpanse/sage-engine` the same
day. Per-phase notes: `docs/dev/milestones/M2-sage-decoupling/phase-{3,4,5}-plan.md`; rulings:
`docs/sage/DECISIONS.md`. The next milestone has not been chosen.

Layout: `engine/src/sage` (server, `python -m sage`), `engine/tests` (`python -m pytest` from the
repo root), `engine/alembic`, `engine/clients/{admin-ui,player-ui}`,
`engine/tools/{worldforge,worldforge-mcp}`, first-party plugins in `plugins/`, world packages in
`worlds/{fablestar,rivermoot}` (content, lexicon, AI prompts/style/ComfyUI graphs, world plugins).

Pre-SAGE status and backlog: `docs/dev/STATUS.md`.
