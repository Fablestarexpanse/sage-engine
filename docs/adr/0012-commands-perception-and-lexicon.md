# 0012 — Commands, perception and the lexicon

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M3 slice 1 (owner ruling: commands first). Agents must act through the same interface players use, and agent memory must be derivable from the log. Both need a command path and a deterministic rule for who perceives what. The blueprint also requires every player-facing string to be overridable per world.

## Decision

**Actors.** `sage.actor` (v1) marks an entity that may submit commands and perceive occurrences. Player characters and synthetic agents are both just actors.

**Commands.** `Scheduler::submit(actor, text)` queues text. At the start of the next step, before any system runs, each queued command is processed in submission order:
- Empty text, or a submitter that isn't a live actor, is reported and never logged.
- Otherwise the command is logged as a `sage.command` occurrence (data `{text}`, perceived only by the actor). The first word is the verb. If no handler owns the verb but the whole text matches a link label out of the actor's place, it means `go <text>`.
- The handler returns proposed events and private output lines. The command and the events commit as one batch.
- If the world refuses the events, the command alone is logged and the actor is told it did not work.
- A handler that errors is suspended, like a system.
- A verb can have only one owner; registering a second claim is refused.

**Core verbs** (owner ruling): `look`, `go`, `say`, `emote`. Directed conversation (`tell`, later `ask`) belongs to the `sage.dialogue` plugin.

**Occurrences.** `Occurred` (v1) is an event that changes no component: `{kind, kind_version, actor, places, targets, data}`.
- **Kind names:** at least two lowercase dotted segments. A plugin's kinds start with its id.
- **Validation:** the world refuses a malformed kind, `kind_version` 0, or any referenced entity that doesn't exist.
- **Core kinds:** `sage.command`, `sage.said`, `sage.emoted`, and `sage.travelled` (places `[from, to]`).

**Perception.** An actor perceives an occurrence if it is the occurrence's actor, one of its targets, or located directly in one of its `places`. That's checked against the world *after* the batch commits, so a traveller's old room sees them leave and the new room sees them arrive. `Scheduler::step` returns `deliveries` for every committed occurrence, from commands and from systems, plus the private output lines.

**Lexicon.** The engine emits `Line { key, params }` and never sentences.
- **Occurrence keys:** `<kind>.self` for the actor, `<kind>.target` for a target, and `<kind>.other.<n>` for an observer in the nth listed place, falling back to `<kind>.other`.
- **Parameters:** `actor`, `target`, and every top-level string or number in the data.
- **Rendering:** `Lexicon::render` fills in templates. A missing name renders as the `sage.name.unknown` template. A key with no template renders nothing, which is how `sage.command` stays silent.
- **Overrides:** `Lexicon::core_english()` holds the defaults, and a world overrides any key.

## Consequences

- Tested with rendered English: look shows name, description, exits and others present; go moves the actor, and the old room, new room and mover each get their own line; the bare label shortcut; speech stays in its place; nonsense is logged, answered, and changes nothing; non-actors can't command; refused handler events leave only the logged command; failing handlers are suspended; verb claims can't conflict; a log of commands replays byte-identically.
- Mutation checks: letting every actor hear every occurrence fails the speech test; ignoring the place index fails both travel tests.
- There's no input path in `sage run` yet. Players arrive over WebSocket at M4, and agents submit through the scheduler in S2.
- Perception covers direct containment only (no hearing through walls or from inside a container). Richer rules would be a fragment's business later.
- `look` and list joining (`", "`) still put some English structure in the engine. They're lexicon parameters, so a world can restyle them, but list grammar isn't localizable yet.
