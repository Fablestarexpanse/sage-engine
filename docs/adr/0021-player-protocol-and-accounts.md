# 0021 — Player protocol over WebSocket, and local accounts

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M4 S1. Owner rulings:
- play comes first
- local per-world accounts with argon2id, kept out of the event log
- a React client embedded in the engine, which is S2

Players need a way into a running world that reuses everything built so far: commands, perception and the lexicon.

## Decision

**`sage run --listen <addr>`** starts a WebSocket server at `ws://<addr>/ws`. There's no network unless asked.
- **Where it binds:** only where the operator says. The documentation example uses `127.0.0.1`.
- **TLS:** not handled by the engine. Public servers belong behind a reverse proxy.
- **Startup line:** `listening ws://<addr>/ws accounts=<path>`, which tests use to find port 0.

**`sage.protocol/1`**: JSON text frames, where a frame must be a JSON object.
- **Client frames:** `register {name, password}`, `login {name, password}`, `command {text}`. Unknown frame types and fields are refused.
- **Server frames:**
  - `welcome {protocol, engine}`
  - `session {name, character}`
  - `line {tick, key, params, text}`: the lexicon key and parameters plus the world's rendering, so clients may reword
  - `state {tick, place, exits, here}`: sent on sign-in and after any tick in which something reached the character
  - `error {code, message}`, with stable codes
  - `kicked {reason}`

**Two threads.**
- **Network thread** (its own tokio runtime; axum). It parses frames, checks name and password form, hashes and verifies passwords with argon2id on blocking threads, and counts failed logins. It never touches the world.
- **Engine thread.** It owns the world and the accounts writes. Before each step it drains requests: it creates characters, signs players in, and submits their commands with `Scheduler::submit`, the same path agents use. After each step it sends each delivery to the player whose character perceived it.

**Accounts.** They live in `<world>.accounts.db`: `name` (unique ignoring case), `password_hash` (argon2id PHC string), and `character`. The event log never contains passwords or hashes (tested).
- **Registering** creates the character as ordinary events: a described actor, located at `--start-place` or else the lowest-numbered place. Those events commit in their own transaction at the current tick.
- **Logging in** re-attaches the character. If the character is gone, a new one is created. A login from a second connection kicks the first.

**Limits:**
- frames at most 4 KiB, and a larger frame closes the connection
- commands at most 512 characters
- at most 3 commands per player per tick; more get `slow-down`
- 5 failed logins per connection, then it closes
- names are 2–24 ASCII letters, digits or hyphens, starting with a letter, and can't match any existing actor's name (agents included)
- passwords are 8–128 characters
- a login for an unknown name still verifies against a real dummy hash, so response timing doesn't reveal which names exist

## Consequences

- **Tested against the real binary with WebSocket clients:**
  - Two players register, see the place, exits and each other, talk, and one hears the other leave.
  - Commands before sign-in, bad names and passwords, unknown frame types, a taken name in any case, an agent's name, command floods, over-long commands and oversized frames are all refused.
  - Wrong passwords close the connection on the fifth try.
  - Logging in again replaces the old connection. After a restart the same account gets the same character.
  - No password or hash text appears in the event log.
- **Bugs found by the tests:**
  - A connection ending right after an error dropped that error, because the writer was aborted; it now drains before closing.
  - Serde accepted a JSON array as a tagged frame; frames must now be objects.
- **Not built yet:**
  - A disconnected player's character stays in the world, idle.
  - There's no admin role or account deletion.
  - Protection against guessing across many connections is left to a reverse proxy.
- **Next:** the browser client is S2.
