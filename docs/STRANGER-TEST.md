# The 15-minute stranger test

The M4 gate (ADR 0004): *a stranger installs the engine, downloads a fragment from the Foundry, and plays, in under 15 minutes.* This is how to run it, what counts as a pass, and what to write down.

## Who runs it

Someone who has not worked on SAGE. They may read the releases page, the Foundry and [QUICKSTART.md](QUICKSTART.md), and nothing else. Whoever watches does not help, hint or type. Questions are answered only with "do what you think is right", and the question goes in the notes: every question is a documentation bug.

## Before starting

- v0.1.0 is published, with archives and `SHA256SUMS`.
- The Foundry is live, and its fragment page shows an install command.
- The tester's machine has never run SAGE: no `sage` binary, no world files, no Node, and no model server.
- A stopwatch, and somewhere to write notes.

## The run

Start the clock when the tester opens the releases page.

1. **Download and unpack** the archive for their computer, and check it against `SHA256SUMS`.
2. **Start a world:** `sage run my-world.db --seed worlds/demo-agents/seed.json --plugin plugins/sage.dialogue --listen 127.0.0.1:4700`.
3. **Play:** open <http://127.0.0.1:4700/>, create a character, and try `look`, `say good day` and `go onward`.
4. **Bring in a fragment:** stop the world, open the Foundry, pick a character, copy its install command, run it, then `sage place …`.
5. **Play again:** start the world and talk to the character they installed, by name.

Stop the clock when the installed character answers them.

## Pass

- Under 15 minutes, hands-off.
- No step needed a command that isn't on the releases page, the Foundry or the quickstart.
- Nothing the tester saw was a crash, a stack trace, or an error with no next step.
- The world still passes `sage inspect` afterwards: `snapshot_matches_replay` is true.

## Write down

- Total time, and the time at the end of each numbered step.
- Every question asked, and every place the tester paused, backtracked or guessed.
- Anything that looked like an error, copied exactly.
- The operating system, and whether SmartScreen or Gatekeeper got in the way.
- What they tried that we never thought of.

A failed run is worth as much as a passing one: fix what it found, then run it again with a different stranger. Record each run in [DECISIONS.md](DECISIONS.md), and the result of the gate in [STATUS.md](STATUS.md).

## Rehearsal

The same path can be rehearsed locally, which catches broken commands but not confusion:

```bash
sage registry build registry/inputs site/registry     # or use the Foundry repo's committed one
python -m http.server -d site 8000                    # stand-in for the Foundry
sage run my-world.db --seed worlds/demo-agents/seed.json --hz 4 --until-tick 1
sage install my-world.db fragmentfoundry.tamsin-reed --registry http://127.0.0.1:8000/registry
sage place my-world.db fragmentfoundry.tamsin-reed
sage run my-world.db --plugin plugins/sage.dialogue --listen 127.0.0.1:4700
```

A rehearsal never counts as the gate: the gate is a person who has not seen this before.
