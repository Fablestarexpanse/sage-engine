# 0004 — Bottom-up build order with milestone gates

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

v1 built three clients and an MCP surface before its world model was stable. Most of its decision log was spent patching that.

## Decision

Build in this order: world model, event log, plugin seal, agents, then clients and editors. No code for a layer merges until the gate tests of the layer below pass. Gate criteria come from blueprint §I and §D2:

| Milestone | Gate (every item is a test or a recorded run) |
|---|---|
| M1 World model | A 4-place world with 100 entities runs 24 h. After kill -9, restart rebuilds state from the log. Replay reproduces the snapshot byte for byte. A log written before a deliberate event-schema change replays through an upcaster. Every stored event carries `schema_version`. |
| M2 Plugin seal | A plugin with an undeclared import fails at boot. Fuel exhaustion suspends the plugin while the world keeps running. Manifest validation gives identical results native and in WASM. `sage check` exists. A plugin built against WIT N-1 boots through an adapter. |
| M3 Agents | Ten scripted agents run offline for 1 h. An LLM agent passes the same-command-interface test. The demo world plays with all AI disabled, in CI. |
| M4 Client + Foundry MVP | A stranger installs the engine, downloads a fragment and is playing in under 15 minutes. |
| M5 Workshop + social | A non-programmer publishes an agent card without using a terminal. |
| M6 Marketplace | A paid fragment is sold and installed, with no DRM. |

Not built in engine v1: combat, levels, classes, magic, factions, weather, crafting or economy in core. Also no native plugin tier, no Redis or any second store, no desktop editor, no client JavaScript shipped by plugins, no hosted worlds, and no more than one client.

## Consequences

The first visible UI arrives late on purpose. Progress before M4 is measured by gate tests, not screens.
