# 0011 — Plugins in `sage run`, first-party `sage.wander`, M2 closed

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** the `harness.wander` test system from 0007

## Context

M2 slice 3: a world has to actually run with plugins loaded from fragment directories. The M1 test-harness system has to go, as ADR 0007 promised. And the M2 gate needs a verdict.

## Decision

**`sage run --plugin <fragment-dir>`** (repeatable; plugins run in the order given). Each plugin must pass `sage check` first; otherwise the run stops and prints the check report. It then loads with exactly the capabilities its manifest declares. Plugins are checked and loaded *before* the world file is opened, so a refused plugin never creates or seeds a world (tested).

**`sage.wander`** (`plugins/sage.wander/`) is the first first-party plugin: `fragment.yaml` plus a Rust crate. Every 20 ticks it moves each located entity along the first link leaving its container. The interval is a constant because plugins have no configuration yet. `harness.wander` and `--wander-every` are deleted. The kill -9 restart gate now runs the real plugin instead of native code.

**`sage-build`** (renamed from `sage-fixtures`; never published) builds WASM components from source:
- `sage-build plugins` builds every first-party plugin into `target/plugins/<id>/{fragment.yaml, plugin.wasm}`.
- Tests use the same functions to build the first-party plugins, the test plugins (now in `crates/sage-build/test-plugins`) and the schema validator.
- The crate for plugin `creator.slug` is named `creator-slug`.

**`sage.dialogue` is deferred to M3.** Dialogue needs a command interface and perception, which arrive with agents. A dialogue plugin built now would have nothing to be called through, so its shape would be a guess. It's the first plugin M3 builds.

**M2 is closed.** Gate items from ADR 0004:
- **Plugin with an undeclared import fails at boot:** passed. It's refused at load, naming the interface. The linker alone also refuses it, and `sage run` refuses it through `sage check`.
- **Fuel exhaustion suspends the plugin while the world keeps running:** passed. The memory cap does the same.
- **Manifest validation identical native and in WASM:** passed on 24 inputs, byte for byte.
- **`sage check` exists:** passed, with 8 tests.
- **A plugin built against WIT N-1 boots through an adapter:** deferred by owner ruling to the first real `sage:core` major bump.

## Consequences

- Measured: the demo world with `sage.wander` ran 2,000 ticks with 10,000 moves (100 entities × 100 wander ticks), `refused=0`, and inspect reported that the snapshot matches replay.
- Plugin configuration (for example, making the wander interval a setting) needs a manifest `config` section and a grant to read it. That's a `sage.fragment/2` question, decided when a real plugin needs it.
- Loading a plugin runs its boot check (one dry tick) and then loads it again for real. The cost is milliseconds.
