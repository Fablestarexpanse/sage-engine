# SAGE decoupling — decision log

NEXT: Phase −1 (4 commits) + Phase 0 (144706a) + Phase 1 contracts committed on `sage/phase-0-1`.
Artifact published. STOPPED for owner review of PHASE1_CONTRACTS.md (Part G questions).
Do not start Phase 2 until approved.

Append-only. One entry per ruling or decision, newest last. Owner rulings are binding; architect
decisions are proposals until the Phase 1 review approves them.

| Date | Who | Decision | Why |
|---|---|---|---|
| 2026-09-13 | Owner | Brief received (`docs/sage/BRIEF.md`). Scope of this session: Phase −1, Phase 0, Phase 1, then stop. | Brief §5. |
| 2026-09-13 | Owner | "The standalone map tool" in the brief means the **WorldForge Tauri app** (`worldforge/`). | Brief said map tool built / WorldForge unbuilt; the repo's WorldForge is built and its README calls it the map tool. |
| 2026-09-13 | Owner | Phase 0/1 deliverables live in **`docs/sage/`** in the repo, plus a private Artifact copy. | Versioned with the code. |
| 2026-09-13 | Owner | **Agents (computer-controlled players) become a whole plugin.** The engine knows nothing about them. | Chosen over "engine runtime + world data". Second world can run without agents. |
| 2026-09-13 | Architect | Brief's four Phase −1 bugs are already fixed in the tree; replaced with three audit-found breakages (admin builder drops `floors`, tick errors swallowed, removed commands never unregistered). | Verified by reading code; see PHASE0_AUDIT.md §Phase −1. |
