# SAGE decoupling — decision log

NEXT: Phase −1, 0, 1 done on `sage/phase-0-1`; license applied. Owner answered contracts G.2, G.3,
G.5, G.8. STILL STOPPED: waiting on G.1, G.4, G.6, G.7, G.9, G.10 and explicit approval of
PHASE1_CONTRACTS.md before any Phase 2 work. Review page (private):
https://claude.ai/code/artifact/2d488113-1ca9-4f45-b993-ac0253e0670c

Append-only. One entry per ruling or decision, newest last. Owner rulings are binding; architect
decisions are proposals until the Phase 1 review approves them.

| Date | Who | Decision | Why |
|---|---|---|---|
| 2026-09-13 | Owner | Brief received (`docs/sage/BRIEF.md`). Scope of this session: Phase −1, Phase 0, Phase 1, then stop. | Brief §5. |
| 2026-09-13 | Owner | "The standalone map tool" in the brief means the **WorldForge Tauri app** (`worldforge/`). | Brief said map tool built / WorldForge unbuilt; the repo's WorldForge is built and its README calls it the map tool. |
| 2026-09-13 | Owner | Phase 0/1 deliverables live in **`docs/sage/`** in the repo, plus a private Artifact copy. | Versioned with the code. |
| 2026-09-13 | Owner | **Agents (computer-controlled players) become a whole plugin.** The engine knows nothing about them. | Chosen over "engine runtime + world data". Second world can run without agents. |
| 2026-09-13 | Architect | Brief's four Phase −1 bugs are already fixed in the tree; replaced with three audit-found breakages (admin builder drops `floors`, tick errors swallowed, removed commands never unregistered). | Verified by reading code; see PHASE0_AUDIT.md §Phase −1. |
| 2026-09-13 | Owner | **One database per world** (contracts B.8 accepted). | Only way to keep "no `world_id` columns" and "switch worlds = config + restart" together. |
| 2026-09-13 | Owner | **Glyph, ship, star-system and galaxy surfaces are not needed at this time** — delete them (models, editors in WorldForge and admin-ui, glyph admin tab, mock client panels) when Phase 3/5 reaches them. Recoverable from git if the design later wants them as a Fablestar plugin content type. | No content, no runtime (audit §11.7); brief §8 prefer deleting. |
| 2026-09-13 | Owner | **Rename approved.** Official name: **"SAGE - Synthetic Agent Game Engine"**; Python package `sage` in Phase 2b per contracts F.1. | Answers contracts G.5. |
| 2026-09-13 | Owner | **License: Functional Source License, `FSL-1.1-Apache-2.0`, engine only.** Licensor Brian M. Taylor. Fablestar world content stays proprietary, all rights reserved. Spec: owner's `sage-fsl-license-setup.md` (applied in commit after this entry). No commercial-waiver contact yet (step 7 skipped). | Replaces the undeclared MIT in `pyproject.toml`; answers contracts G.8. |
| 2026-09-13 | Architect | License applied with three deviations from the owner's spec, all forced by the canonical text: (1) the official identifier is `FSL-1.1-ALv2`, not `FSL-1.1-Apache-2.0`; (2) the template has only `${year}` and `${licensor name}` placeholders, so "SAGE" is named in `NOTICE`/`LICENSE-FAQ.md` rather than inside `engine/LICENSE`; (3) year set to 2026 (not yet published — revisit at first publication). `engine/LICENSE` is byte-identical to `https://fsl.software/FSL-1.1-ALv2.template.md` (sha256 36b60822…56177) except the copyright line. Because `engine/` and `worlds/` don't exist yet, `NOTICE` maps today's paths to each component and excludes Fablestar material still embedded in engine paths. | Owner spec step 2 said confirm layout first. |
| 2026-09-13 | Architect | **Flag for legal review, not resolved:** the owner's FAQ promise "you can build and sell your own game/world on SAGE" is not stated in the FSL text, and Competing Use clause 2 ("substitutes for any other product or service we offer using the Software") arguably covers a commercial MUD because Fablestar Expanse exists. `LICENSE-FAQ.md` states the intent and marks it pending legal review. Options for the owner: accept the ambiguity, add an explicit additional permission alongside the license, or get counsel. Also: don't publish `engine/` until Phase 3 has extracted Fablestar content from engine paths. | Brief §8: flag, don't guess. |
