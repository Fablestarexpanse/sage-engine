# 0014 — The Mind component and scripted agents

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M3 S2. Owner rulings: scripted behaviour is an ordered rule list stored as data, and perceptions between thinks live in an in-memory inbox until S3. ADR 0004's gate asks for ten scripted agents running offline for an hour. Per the owner's no-long-waits preference, that's one hour of *world* time in fast mode.

## Decision

**`sage.mind` (v1)**, owned by `sage-agents`. It's registered by `sage_agents::registry()`, which `sage run`, `inspect` and `check` all use.
- **Fields:** `driver` (only `scripted` for now), `think_every`, `persona`, `goals` and `rules`.
- **Rule conditions:** `heard` (an occurrence kind perceived since the last think, not done by the agent itself), `text_contains` (requires `heard`), `every`, `chance`, `alone`.
- **Command template:** `do`, with the variables `{speaker}`, `{text}`, `{any_exit}`, `{any_actor}` and `{self}`. If a variable can't be filled, the rule doesn't fire. `{speaker}` and `{text}` require `heard`.

**Component validation hook.** `Component::validate` lets any component reject bad data. The world refuses it exactly like data that doesn't deserialize, so an event or a snapshot can never carry an invalid component. `Mind` rejects:
- unknown drivers or unknown fields
- `think_every` of 0, or `every` of 0
- `chance` outside 0 to 1
- `text_contains` without `heard`, and unknown or unsatisfiable template variables
- unclosed braces, and empty commands
- more than 64 rules or a persona over 4,000 characters

**Scripted driver.** The first rule whose conditions all hold produces one command.
- **Chance and picks** (`any_exit`, `any_actor`) come from a splitmix64 hash of (agent, tick, rule), written out in the code and pinned by a test, so a world's history can't change with the Rust version.
- **Filling templates** is a single pass, so heard text containing `{self}` or `{any_exit}` is never expanded (tested).

**Runner.** `Agents::observe(world, report)` keeps deliveries addressed to agents, up to 64 each. `Agents::think(world, tick)` lets due agents decide, in id order. An agent is due when `(tick + id) % think_every == 0`, which staggers agents that share an interval. It returns commands the caller submits through `Scheduler::submit`, the path players use. `sage run` does this after every step, so an agent that perceives something at tick t acts at t+1 (tested). A thinking agent's inbox is emptied. An entity with a mind but no `sage.actor` never acts.

**`worlds/demo-agents`** is the demo world plus ten zero-AI agents (ids 109–118) with varied thinking rates. They greet whoever says "good day", answer `tell`, greet others now and then, look around, and wander. The rules are written so replies don't trigger further replies.

## Consequences

- **Gate** (`crates/sage-server/tests/agents.rs`, with `sage.dialogue` loaded): 14,400 ticks in 16.5 s.
  - 4,436 agent commands, every agent between 318 and 575.
  - 1,823 moves, 2,209 speech lines, 402 emotes.
  - `refused=0`, nothing suspended, and the snapshot matches replay.
  - Only agents issued commands, all logged as `sage.command`.
- Tests also cover:
  - Agents don't answer themselves; with that guard removed by mutation, the test fails.
  - A wandering agent's run is byte-identical when repeated, log included.
  - The `alone` and `every` conditions.
  - Minds without an actor don't act.
  - Nine kinds of invalid mind are refused.
- The inbox is lost on restart, so a restarted world with `heard` rules can differ from an uninterrupted one. The kill -9 test uses the agent-free demo world. S3 makes memory a projection of the log, which removes this gap.
- The runner lives in `sage run`, not in `Scheduler`, so the core has no knowledge of agents. A client-driven server at M4 does the same.
