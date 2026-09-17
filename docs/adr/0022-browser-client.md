# 0022 — Browser client, embedded in `sage`

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M4 S2. Owner ruling: React + TypeScript + Vite, embedded in the `sage` binary. Players need a way to play from a browser without installing anything but the engine. The client must be keyboard first, and every panel must have a text equivalent.

## Decision

**`client/`** is a Vite app. It uses React 19, TypeScript 7 and Vite 8, with vitest 5, Testing Library and jsdom for tests. The package manager is pnpm, with the lockfile committed.
- **`protocol.ts`:** a pure reducer from `sage.protocol/1` frames to session state. It keeps the log capped at 500 lines. It never stores a password: `sent` echoes only commands. A `welcome` with a different protocol version is shown as an error.
- **Sign-in screen:** log in, or create a character, with the server's name and password rules mirrored as form constraints. The server still checks everything.
- **Play screen:**
  - the log, `role="log"`, `aria-live="polite"`, with echoed commands
  - a command box with up and down history (100 entries)
  - a side panel with the place, exit buttons that send the exit label as a command, and who is here
  - everything in the panel also arrives as text lines in the log
- **Connection:** the client connects to `ws(s)://<page host>/ws`. It shows its connection state, and offers Reconnect when the socket closes.
- **Enter:** Enter on keydown submits the form and cancels the default, so it submits exactly once even from an input method that sends no keypress. An Enter that ends an IME composition is left alone. The in-app browser used for the real run sends keydown alone, which is how this was found.

**Embedding.** `crates/sage-server/build.rs` reads `client/dist` (or `SAGE_CLIENT_DIST`) and generates an `include_bytes!` table.
- **Rust builds don't need Node:** with no client built, `sage` serves a page saying how to build it. `/ws` works either way.
- **Rebuild trigger:** the build script creates the empty `client/dist` directory if it is missing and watches it. A missing watched path would make cargo rerun the script, and rebuild the crate, on every build.
- **Startup line:** it gains `play=http://<addr>/ client=embedded|not-built`.

**Serving.** An axum fallback beside `/ws` serves only the embedded files; nothing is read from disk at runtime, so paths such as `/../Cargo.toml` are simply not found.
- **Headers on every response:**
  - `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: no-referrer`
- **Build output:** Vite is set to inline no assets, so the policy needs no `unsafe-inline`.
- **Caching:** `/assets/*` (content-hashed names) is cached as immutable; everything else is `no-cache`.

**CI.**
- **Client job:** typecheck, test and build the client.
- **Rust job:** builds the client first, so the tested binary is the shipped one with the client embedded.
- **Denylist:** it now also scans `client/src`.

## Consequences

- **Tests.**
  - Client (vitest, 11): the reducer (sign-in, lines without wording hidden, passwords never kept, state frames, errors cleared by the next action, protocol mismatch, kick and disconnect, log cap), frame parsing, socket URL, and the app against a fake socket. The app tests cover registering, keyboard play with history, exit buttons, Reconnect, and a bare Enter keydown sending exactly once. Removing the Enter handler fails 2 of them.
  - Engine: `the_client_is_served_on_the_same_port_under_a_strict_policy` runs against the real binary. It checks the page, the policy, `nosniff`, 404s for paths outside the client, the script's content type and caching, and that `/ws` still answers. It passes both with and without a built client.
- **Real run** (Windows, the in-app browser, demo-agents world at 10 Hz):
  - Created a character and saw the place, exits and the 10 agents. Agents greeted the player by name.
  - After a server restart, logged in by keyboard alone, said something, looked, and recalled history with the arrow keys.
  - Moved with the exit button.
  - At 375 px wide there is no horizontal scroll.
- **Bugs found by the real run:**
  - Enter did not submit when the browser sent no keypress (fixed as above).
  - At phone width the log covered the place panel (fixed: the panel row sizes to content, capped at 30% of the height).
- **`client/pnpm-workspace.yaml`:** pnpm 11 wrote a `minimumReleaseAgeExclude` entry for `jsdom@30.1.0`, which is newer than pnpm's default minimum release age. It is a test-only dependency.
- **Not built yet:** clickable names in the log, colour or styling from the lexicon, and a transcript download.
- **Next:** S3, fragment packages, `sage install` and Tavern Card import.
