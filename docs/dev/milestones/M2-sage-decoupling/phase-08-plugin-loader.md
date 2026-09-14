# Phase 08: Plugin loader and sage.api

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** phase-07
**Tags:** language=python, kind=feature, size=l

## Goal

Contracts Part C: a world enables plugins in `world.toml [plugins]`; the engine discovers,
validates, orders, loads and seals them, and gives each a scoped API. This is the mechanism
Phase 3 uses to move Fablestar systems out of the engine, and the second reference world's
`levels` plugin (phase 09) is its first real consumer.

## Spec (as built)

1. `sage.plugins.manifest`: `plugin.toml` schema (`[plugin]` id/version/engine/entry/first_party,
   `[depends]` with `"^1"` shorthand and `optional`, `[touches]` with every contract field;
   kinds this engine supports: commands, events_publish, events_subscribe, resolvers_define,
   resolvers, tick_jobs, state_blocks, services, lexicon_prefix).
2. `sage.plugins.loader`: locate (world-private `worlds/<w>/plugins/<id>` shadows
   `plugins/<id>`), engine and requested version ranges, required/optional dependencies,
   deterministic topological order with cycle detection, import by path under
   `sage_plugins.<id>` / `sage_worlds.<w>.plugins.<id>`, trust banner for anything not
   first-party inside the trusted roots, lexicon layer with enforced key prefix, seal.
3. `sage.plugins.api.PluginAPI`: `commands.register`, `events.subscribe/publish`,
   `resolvers.define/provide/get`, `tick.every`, `state.block/get/set`, `services.provide/get`
   (only from declared dependencies), `param` (namespaced), `t`, `log`, `withdraw`.
4. `sage.plugins.PluginHost`: `load()` (setup failure withdraws and tears everything down),
   `lexicon_layers()`, `teardown()` (calls optional `teardown(api)` in reverse order).
5. `SageServer`: host built in `__init__`; plugins load in `startup()` after engine commands,
   lexicon rebuilt with plugin layers; teardown on shutdown. `sage.api` re-exports the stable
   surface. `CommandRegistry.unregister`; `Resolvers.withdraw` also removes owner-defined slots.

Deferred to later phases (declared in the schema, refused if used): content types, content
extensions, snapshot sections, HTTP routes, panels, tables/migrations, Redis prefixes, AI slots.

## Update Log

### Update — 2026-09-13 (complete)

422 passed + 5 skipped (12 loader tests: register/teardown, seal rollback, dependency order,
missing dependency, cycles, version and engine ranges, world-private shadowing, trust banner,
lexicon prefix, service dependency rule, state blocks and params). Real server boots and plays
with the plugin host active (Fablestar enables no plugins yet).
