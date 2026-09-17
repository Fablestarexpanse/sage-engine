# 0020 — M3 closed; Tavern Card import moves to M4

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** the S4 item of the M3 plan (DECISIONS, "M3 plan")

## Context

The M3 plan was S1 commands and perception, S2 scripted agents, S3 memory and LLM, and S4 Tavern Card v2 import. S1–S3 are done (ADRs 0012–0019). Owner ruling: card import is a content-fragment format and moves to M4, alongside the fragment package format, install and publish. M3 closes.

## Decision

**M3 is closed.** ADR 0004's M3 gate:
- **Ten scripted agents run offline for 1 h:** passed in fast mode, as the owner prefers. 14,400 ticks, `refused=0`, snapshot matches replay (`crates/sage-server/tests/agents.rs`).
- **An LLM agent passes the same-command-interface test:** passed against stub OpenAI-compatible servers, in the library and through the real `sage` binary. A model's answer is submitted as an ordinary command and logged as the agent's `sage.command` (`crates/sage-agents/tests/llm.rs`, `crates/sage-server/tests/llm.rs`).
- **The demo world plays with all AI disabled, in CI:** passed. `worlds/demo-agents` runs with scripted agents and no model, and model-driven minds fall back or stay idle without one.

**Beyond the gate, M3 also delivered:**
- a command interface with perception and a lexicon, plus plugin commands (`sage.dialogue`)
- memory projected from the log, with each occurrence's audience recorded (`Occurred` v2, the first real schema change, with an upcaster proven on an old-build log)
- each tick as a single transaction
- component upcasters
- deterministic importance and retrieval
- embeddings with a rebuildable cache
- reflection

**Moved to M4:** Tavern Card v2/v3 PNG import. That covers:
- chunk reader (`chara`, `ccv3`), fuzzed
- detection of the card type from its structure
- mapping onto `sage.mind` and seed memories
- the PNG content-fragment format itself

## Consequences

- **Not verified against real models:** everything model-related is tested against stubs. The first run with a real chat model and a real embedding model is still owed, and results may prompt tuning of prompts, thresholds and timeouts.
- **Plans deferred:** agent plans (the planning half of Generative Agents) were deferred by owner ruling and are not scheduled.
- **Next:** M4 (client and Foundry MVP) starts with a plan agreed with the owner, per ADR 0004.
