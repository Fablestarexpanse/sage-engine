# 0013 — Plugin command handlers and `sage.dialogue`

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M3 S1 part 2. Owner ruling: directed conversation lives in the `sage.dialogue` plugin, not in core. Plugins therefore need to add commands, ship default wording, and emit occurrences, without being able to impersonate core or other plugins.

## Decision

**WIT, additive.** `sage:core@0.1.0` gains an interface and a world:
- `interface commands`: `verbs()`, `lexicon()` (default templates as key/template pairs), and `handle(actor, verb, args, tick) -> result<outcome, string>`. An outcome holds proposed events and private output lines.
- `world command-plugin`: `include plugin; export commands;`.

Existing interfaces and the `plugin` world are unchanged, so every existing plugin still loads. The version stays 0.1.0 because nothing has been published. Once a first release is published, every WIT change bumps the version.

**Host.** `PluginHost::load` instantiates once, and a plugin's system and command handler share that instance (`Rc<RefCell>`). A trap in either one poisons the instance, and neither is called again. Command-plugin bindings reuse the plugin world's import bindings (`with:`), so the host functions exist once. The host also enforces:
- lexicon keys must start with `<plugin name>.`, checked at load
- output line keys must start with `<plugin name>.`
- every `Occurred` a plugin proposes, from a system or a handler, must have a kind starting with `<plugin name>.`

Together with `sage check`'s rule that the name equals the manifest id, a plugin can't speak as core (`sage.said`) or as another fragment.

**`sage check`** also fails a plugin whose handled verbs differ from `provides.commands` (in either direction), or whose verbs clash with core verbs.

**`sage run`** registers each plugin's handler before adding its system. A verb conflict between plugins stops startup.

**`sage.dialogue` 0.1.0** (`plugins/sage.dialogue`) handles `tell <name> <text>`. The target must be an actor in the same place whose name matches, ignoring case. It emits `sage.dialogue.told` with `targets: [target]` and no places, so only the teller and the target perceive it. Its lexicon covers `told.self`, `told.target`, `tell.usage` and `tell.nobody`. `ask` and topics wait for agents (S2/S3) to have something to answer with.

**Test plugin assembly.** `sage_build::first_party_plugin` assembles into a per-process directory under `target/sage-build-plugins/fragments/<pid>/`, once per id. That stops parallel test binaries writing a file another is reading. `sage-build plugins` still writes `target/plugins/`.

## Consequences

- Tested with the real plugin:
  - `tell` is heard by the teller and the target, not by a third actor in the same room or by anyone elsewhere.
  - The usage and nobody-here messages render from the plugin's own lexicon.
  - The log replays byte-identically.
  - Two plugins can't claim the same verb.
  - System-only plugins have no handler.
  - The `impostor` test plugin's `sage.said` is refused with the prefix rule named.
  - `sage check` fails a manifest whose `provides.commands` doesn't match.
- A real run with `sage.wander` and `sage.dialogue` loaded together starts, runs and stops cleanly.
- Names are matched on the first word only, so multi-word names can't be targeted yet.
- Rendering the merged lexicon (core, then plugins, then world overrides) is the client's job at M4. The server doesn't render yet.
