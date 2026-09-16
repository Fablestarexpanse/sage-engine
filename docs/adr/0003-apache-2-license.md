# 0003 — Apache-2.0 with a CLA

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** v1's FSL-1.1-ALv2 (see 0001)

## Context

v1's FSL "competing use" clause contradicted the promise that people can build and sell worlds and fragments on SAGE, and no written assurance could fully remove that doubt.

## Decision

- Engine, first-party plugins, the demo world and fragment templates: **Apache-2.0**.
- Contributions from others require a CLA. The text in `CLA.md` is a placeholder until a lawyer reviews it, and outside PRs cannot merge until then.
- Every fragment manifest carries an SPDX license id or a `LicenseRef-*` (for example `LicenseRef-AllRightsReserved` for paid content).
- Fragment Foundry's site code is a separate repository with its own license decision.

## Consequences

- Anyone can sell worlds and fragments built on SAGE with no license question.
- Someone could fork the engine and offer it as a hosted service. That is accepted, because the business is the Foundry, not the engine.
- Needs a lawyer: the CLA text, the AI-generated content and likeness policy, and the merchant-of-record contract.
