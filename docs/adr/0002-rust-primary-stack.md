# 0002 — Rust as the engine language, no TypeScript spike

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

The blueprint compared Rust, TypeScript/Node, Elixir and Python for a solo developer who builds with AI coding assistants. It recommended Rust and suggested a two-week M1 spike in both Rust and TypeScript as insurance.

## Decision

Rust, with no spike. Planned stack:

- ECS: `bevy_ecs`, used standalone with no renderer
- Event log and snapshots: SQLite in WAL mode via `rusqlite`
- Plugin host: Wasmtime with the Component Model. WIT imports are the seal. Fuel and epoch limits apply.
- Transport: `axum` + WebSocket (M4)
- Toolchain pinned in `rust-toolchain.toml`, edition 2024

A dependency enters the workspace only when the milestone that needs it starts.

## Consequences

- The compiler acts as a second reviewer on assistant-written code. The cost is slower early iteration.
- The same `sage-schema` crate compiles to WASM, so Fragment Foundry and the browser editors validate with the engine's own code.
- The TypeScript fallback in the blueprint stays documented and unbuilt. Reopen this decision only if M1 stalls, and do it with a new ADR.
- Python stays out of the engine. It is allowed only in offline tooling.
