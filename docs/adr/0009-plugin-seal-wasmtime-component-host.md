# 0009 — Plugin seal: Wasmtime component host

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M2's first slice has to prove the riskiest claim in the blueprint: a community plugin can run inside the world, can't touch anything it wasn't granted, and can't take the world down.

## Decision

**WIT package `sage:core@0.1.0`** (`wit/core/sage-core.wit`):
- `types` holds only type definitions: `entity-id` and `event-record`.
- `entities` and `space` are read-only imports for components, entities by component, links and contents.
- A plugin exports `system` with `name` and `run(tick) -> result<list<event-record>, string>`.
- `world` and `from` are WIT keywords, so the interface is `entities` (the blueprint's own name) and the link field is written `%from`.

**JSON at the boundary.** Component data and event payloads cross as JSON strings in exactly the shapes the log stores. The host decodes plugin output with `Event::from_record`, the code that reads the log, and the world then validates the events like any other. A plugin has no write API: it can only propose events.

**The seal, twice.** `PluginHost::load(wasm, grants, limits)` rejects any grant that isn't in `GRANTABLE`. It then reads the component's imports and refuses the first one not granted, naming it. `sage:core/types` is always allowed because it has no functions. The linker is built with granted interfaces only, so if that check were removed, instantiation would still fail. Mutation-tested: with the check disabled, the plugin is still refused, with "function implementation is missing". A plugin needs no grant for an interface it never imports.

**Limits.**
- Fuel is reset to `fuel_per_call` (default 10M) before every call. Fuel is deterministic; epoch interruption isn't, so it isn't used.
- The memory cap (default 16 MiB) is enforced by a store limiter with `trap_on_grow_failure`, reported as "memory cap exceeded (N bytes)".
- Out of fuel is reported as "out of fuel (budget N per call)".

**Suspension.** `System::run` now returns `Result<Vec<Event>, String>`. The scheduler suspends a system after any error: a trap, fuel, memory, a plugin error, or an undecodable event. It keeps running the other systems and lists suspensions in `StepReport::suspended`. A well-formed event that the world rejects is a *refusal*, not a suspension, same as for native systems. Suspension lasts until the process restarts.

**World handle.** A Wasmtime `Store<T>` can't hold a borrow, so `Journal` now holds `Arc<World>`. `System::run` receives `&Arc<World>`. A plugin puts a clone in its store for the call and drops it before returning, even when the call traps. `Journal::commit` needs the only reference and panics if a handle leaks, which would be a host bug.

**No WASI.** Plugins are built for `wasm32-unknown-unknown` and wrapped into components. There's no ambient filesystem, clock, network or randomness. A plugin that imports WASI is refused like any other ungranted import.

**Test plugins** live in `crates/sage-host/fixtures`, a separate cargo workspace excluded from the main one. The host's tests build them and wrap them with `wit-component`, so no binaries are committed. There are four:
- `mover` reads entities and space and proposes moves.
- `spinner` loops forever.
- `hog` allocates without limit.
- `forger` proposes a refused event, then an unknown event type.

## Consequences

- Measured: `mover` used 64,318 fuel to move 3 entities, with one host call per read.
- Events a plugin proposes replay from the log without the plugin present: tested with a byte-identical genesis replay.
- CI needs the `wasm32-unknown-unknown` target, now declared in `rust-toolchain.toml` and the workflow. Building wasmtime makes a cold CI build noticeably slower.
- Open: the N-1 WIT adapter test waits for the first real `sage:core` major bump (owner ruling). Manifests, `sage check`, and loading plugins from `sage run` come in slices 2 and 3. Per-plugin fuel accounting across a whole tick, instead of per call, is left for when a plugin makes more than one call per tick.
