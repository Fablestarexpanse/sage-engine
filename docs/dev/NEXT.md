# NEXT

Active milestone: **M2 — SAGE engine decoupling** (`docs/dev/milestones/M2-sage-decoupling/`).

Active phase: **none — stages 2a and 2b complete.** Stage 2a is in PR #7; stage 2b (package
`sage`, engine under `engine/`) is on branch `sage/stage-2b`. Next: stage 2c phase docs (plugin
loader, lexicon, world loader, resolver registry, real event bus, state blocks, skeleton second
world).

Layout after 2b: `engine/src/sage` (server, `python -m sage`), `engine/tests`
(`python -m pytest` from the repo root), `engine/alembic`, `engine/clients/{admin-ui,player-ui}`,
`engine/tools/{worldforge,worldforge-mcp}`. World content, config and prompts are still at the
root until Phase 3.

Phase 1 contracts were approved by the owner on 2026-09-13 (`docs/sage/PHASE1_CONTRACTS.md`,
amendments in Part H). Rulings log: `docs/sage/DECISIONS.md`. Stage 2a (CI and ratchets) is done;
stages 2b and 2c get phase docs next.

Pre-SAGE status and backlog: `docs/dev/STATUS.md`.
