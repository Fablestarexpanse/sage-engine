# QA Playtest Report — 2026-09-13

> **Historical record (marked 2026-09-13).** Kept as written for the reasoning trail; do not
> treat as current instructions. Superseded by: `docs/dev/QA_FIX_PLAN_2026-09-13.md` (all steps done) and `docs/dev/STATUS.md`.

Hostile-new-player playtest of the live server (Tidegate Isle test world, 8 LLM agents running, embedded Qwen2.5-3B narration on).
Driven over the `/play` WebSocket by a scripted two-client harness (a "tester" and a "watcher" on separate accounts) plus direct REST calls against Nexus.
Every quoted input/output below is copied from the raw transcript.

## Summary

**What was played:** registration and character creation abuse; the full parser abuse pass (abbreviations, case, whitespace, punctuation, prepositions, injection, 10k-char input, 500-command floods); movement, look variants, and multiplayer visibility with two clients; disconnect and double-login collisions; a player character named after a live agent; proficiency raise/lower/lock; simultaneous take and simultaneous last-unit shop buy; shop, currency, and rent edges; combat against drones; content and command hot reload; Nexus rejection of invalid admin saves.

**What's solid:**
- Character-name regex (empty, unicode, emoji, markup, SQL-ish, over-length all rejected).
- Starter allocation validation (overspend, negative, text, unknown leaf, huge ints).
- No item duplication from simultaneous `take`, same-session take bursts, or a simultaneous buy of the last secondhand unit (one client got `Someone just bought the last pint of algae stout.`).
- Clean disconnects leave no ghost in the room set; reconnect restores position.
- Injection strings are inert: the player client renders chat as text, `|item:…|` links in chat don't become links, and nothing crashed.
- Content hot reload and command hot reload both reach connected and new sessions.
- Nexus rejects invalid personas, unknown backends/rooms/items, and forge path traversal.

**Top 3 fixes:**
1. **QA-01** — block player character names that match agent personas (case-insensitive) and make character names case-insensitively unique. Today a player can take over an agent's live state and copy it into a permanent DB row.
2. **QA-02** — a double login leaves the surviving session invisible and deaf, because the kicked session's teardown removes the character from its room.
3. **QA-03** — player combat blocks on the LLM for several seconds and then shows only LLM prose, which drops the damage numbers and sometimes reverses who hit whom.

## Defects

| ID | Severity | Area | Title |
|---|---|---|---|
| QA-01 | S1 | Accounts / Agents | Player can create a character with an agent's name and hijack and duplicate the agent's state |
| QA-02 | S1 | Sessions | Double login: the kicked session's teardown removes the survivor from the room |
| QA-03 | S2 | Combat / LLM | Player attacks block on LLM narration, and the narration replaces the factual result |
| QA-04 | S2 | Parser | All command arguments are lowercased, including free text in `say` |
| QA-05 | S2 | Comms | `tell` can't address multi-word names; prefix match can resolve to the sender |
| QA-06 | S2 | Spawning / Maestro | Maestro ambush spawns ignore `max_count`, so mobs pile up (15 gullwings where the cap is 2) |
| QA-07 | S2 | Nexus / Forge | `POST /forge/inject` writes syntactically invalid YAML into live content and returns 200 |
| QA-08 | S3 | Nexus / Agents | Admin `give` accepts `digi = -999999` |
| QA-09 | S3 | Accounts | 5000-char username on register returns HTTP 500 — **fixed** |
| QA-10 | S3 | Narration | "The scene:" LLM narration fires after every look and move; it arrives late, describes the wrong room, and contradicts content |
| QA-11 | S3 | Movement | No arrival or departure messages for other players in the room |
| QA-12 | S3 | Look | `look <target>` ignores its argument; `look at` can never match; `examine <player>` unsupported |
| QA-13 | S3 | Input safety | No input length cap, no flood throttle, and ANSI escapes are relayed raw to other players |
| QA-14 | S3 | Accounts | Reserved and confusing character names allowed (`admin`, `north`, `look`, `Qa-`) |
| QA-15 | S3 | Accounts | Password minimum is 8 at the API but 4 in the service |
| QA-16 | S3 | Player client | Narrative auto-scroll yanks the reader down; Tab completion suggests commands that don't exist; narrative log is uncapped |
| QA-17 | S4 | Combat | `flee` moves you even when nothing is hostile |
| QA-18 | S4 | Map | `map` prints 31 `[?] unexplored` lines, leaking zone size as noise |
| QA-19 | S4 | Onboarding | First screen gives no hint that `help` exists |

---

### QA-01 — S1 — Player character named like an agent hijacks and duplicates agent state

**Repro**
1. `POST /play/characters/create` with `{"name": "Sela Varn"}`. The name belongs to a running agent. Response: `HTTP 200 ok=True`. The lowercase `'sela varn'` is also accepted.
2. Log in as that character.
3. Run `score`, `inventory`, `wallet`, then disconnect.
4. As another player, run `who` and then `tell sela are you still there`.

**Expected:** creation rejected with `character_name_taken` for any case variant of an existing character or agent name.

**Actual**
- The clone spawned at the agent's position: `Stairwell — Upper Landing [ aipub:stairwell_f1 ]`.
- It inherited the agent's attributes: `FRT 9  RFX 13  ACU 13  RSV 10  PRS 8`. A fresh character has all 10s.
- It inherited the agent's inventory: `razor crab chitin` ×3 and `depleted power cell` ×4.
- It inherited the agent's wallet: `You carry 96 Digi.`
- After the clone logged out, the agent disappeared from `who` (`Online (8)`, no Sela Varn), and the tell failed: `No one called 'sela' is online.`
- The player `characters` row (id 8) kept tracking the agent afterwards. Its `digi_balance` was 96 at clone logout and 124 at cleanup time, while the agent went on playing. PersistenceManager flushes by name, so the row keeps receiving the agent's live wallet and items. That is a standing duplication path.

**Evidence:** transcript sections "Pass 1b" and "Pass 3e/3f". DB query before cleanup: `(8, 'Sela Varn', 'qa311002', 124)`.

**Root cause**
- Agents and players share one key space keyed by display name: `player:{name}:stats|inventory|location` and `SessionManager.player_to_session[name]`.
- `PlayerService.create_character` checks only `Character.name == name`. That check is case-sensitive and never consults the agent persona registry (`src/fablestar/services/player_service.py:277`).
- On clone login, `kick_existing` evicts the agent's headless session. On clone logout, `destroy_session` deletes the `player_to_session` entry, which leaves the agent detached until a server restart.

**Suggested fix (proposal — multi-file)**
- In `create_character`, reject names that equal any agent persona name case-insensitively. Compare characters with `func.lower(Character.name) == name.lower()`.
- Add a unique index on `lower(name)` in an Alembic migration.
- Defence in depth: `kick_existing` should refuse to evict an `is_agent` session.

**Cleanup done:** the QA accounts and all nine QA characters, including row 8, were deleted, along with their Redis keys. The server was restarted, and agent Sela respawned from `agent_state`: `test_isle:south_road`, `wander: north`.

---

### QA-02 — S1 — Double login: the kicked session's teardown removes the survivor from the room

**Repro**
1. The watcher stands in `test_isle:ferry_landing`. The tester logs in there (room set `['Qa Tester', 'Qa Watcher']`).
2. The tester logs in again from a second connection (`tester#2`). The first socket closes as designed.
3. Wait 3 s, then have the watcher run `look` and `say hello survivor`.

**Expected:** the survivor stays in the room set, is listed under "Also here", and receives the `say`.

**Actual**
- Room set after the collision: `players=['Qa Watcher']`.
- Watcher `look` shows no "Also here: Qa Tester".
- The survivor received `[]` from the say.
- `tester#2`'s own `look` still works; it is invisible to the room, not frozen.

**Evidence:** transcript "Pass 3d".

**Root cause**
- `SessionManager.kick_existing` (`src/fablestar/network/session.py:89`) deliberately doesn't touch Redis room state. However, the kicked session's `run_session_loop` then exits into its `finally` block (`src/fablestar/server.py:658-670`).
- That block reads the *shared* location and calls `remove_player_from_room(session.player_id, room_id)`. The new session is using the same `player_id`, so it gets removed from the room.
- The block also runs `sync_character`. That is harmless now, but it writes from shared state on behalf of a dead socket.

**Suggested fix (proposal):** in the `finally` block, only run room-set cleanup and sync when this session still owns the player, i.e. `session_manager.player_to_session.get(session.player_id) in (None, session.id)`. `kick_existing` has already popped the mapping, so the kicked session would see a foreign owner and skip cleanup. Add a regression test that runs two logins and asserts the room set.

---

### QA-03 — S2 — Player attacks block on LLM narration, which replaces the factual result

**Repro:** walk to `test_isle:drone_gulch`, then send `attack drone` every 1.6 s.

**Expected:** an immediate deterministic line (`You hit feral scrap drone for N damage. It strikes back for M.`), with optional flavour afterwards.

**Actual**
- Most attacks produced `(no output)` inside the 1.6 s window.
- Prose then arrived several commands later with no damage numbers. The actor was sometimes reversed even though the *player* killed the drone:
  > `…As the drone's final strike claimed its prey, the creature's gaunt frame crumpled… feral scrap drone drops: intact drone core.`
- The narration also invents content ("the player's armored fist", "Bone snapped").
- During the same period the early attacks, which fell back to the plain path, read correctly: `You hit feral scrap drone for 4 damage. It strikes back for 5.`

**Evidence:** transcript "Pass 4f", second half.

**Root cause:** `commands/combat.py:255-272` `await`s `llm_client.generate_or_raise(...)` inline in the command handler. The narration is sent *instead of* the fact line; the fact line is only used on exception. This breaks two CLAUDE.md rules: "the game never blocks on LLM output" and "LLMs describe what happened".

**Suggested fix (proposal):** always send the deterministic line immediately. Fire the narration as a background task that appends flavour, the same way the look-scene path already does. Consider dropping combat narration when the embedded backend is busy.

---

### QA-04 — S2 — All command arguments are lowercased, including chat text

**Repro:** `say Mixed CASE Words Here`

**Expected:** `You say: "Mixed CASE Words Here"`

**Actual:** `You say: "mixed case words here"`. The watcher receives `Qa Tester says: "mixed case words here"`.
Also: `say '; DROP TABLE characters; --` shows `"'; drop table characters; --"`, and `say |item:Fake Sword:fake_sword|` shows `"|item:fake sword:fake_sword|"`.

**Root cause:** `parser/tokenizer.py:16,19` calls `input_string.lower()` before splitting. This is documented in CLAUDE.md ("args is a lowercased list"), so every free-text command (`say`, `tell`, `emote`, agent voice replies relayed to players) loses case.

**Suggested fix (proposal):** lowercase only the verb and give free-text commands the raw remainder, e.g. `session.raw_args`, or a `raw=True` flag on `@command`. This is a dispatcher contract change, so it touches several files.

---

### QA-05 — S2 — `tell` can't address multi-word names; prefix match can hit the sender

**Repro (watcher "Qa Watcher", online: Qa Tester, Tessa Moke, …)**
- `tell Tessa Moke hello` gives `You tell Tessa Moke: "moke hello"`
- `tell Qa Tester are you there` gives `You mutter to yourself. It doesn't help.`
- `tell qa hello` gives `You mutter to yourself. It doesn't help.`

**Expected:** match the longest online name prefix of the argument string, then use the rest as the message. Ambiguous prefixes should list the candidates.

**Actual:** only `args[0]` is used as the name. The first name in dict order that starts with it wins, and that can be the sender.

**Not reproduced twice:** once, in "Pass 4g", `tell Qa Tester you there` returned `You tell Qa Tester: "tester you there"` about two seconds after Qa Tester disconnected. A recheck ("Offline tell recheck") resolved to self instead. The first result was probably a session not yet torn down, but it is unconfirmed.

**Root cause:** `commands/communication.py:101-109`.

**Suggested fix (single file, but it changes addressing behaviour, so proposed):**
- Try progressively longer joined prefixes of `args` against the lowercased online names.
- Exclude the sender from prefix matching.
- On ambiguity, return `Which one? Qa Tester, Qa Watcher`.

---

### QA-06 — S2 — Maestro ambush spawns bypass `max_count`, so mobs accumulate

**Repro:** let the server run with agents walking; then `north` ×4 from the plaza to `test_isle:wild_meadow`, then `look`.

**Expected:** at most 2 grey gullwings (`wild_meadow.yaml`: `template: gullwing, chance: 0.4, max_count: 2`).

**Actual:** `Entities: grey gullwing` ×15. Live Redis at report time:

| room | entities | cap |
|---|---|---|
| wild_meadow | 15 gullwing | 2 |
| north_shore | 7 gullwing | 2 |
| orchard | 2 gullwing | — |

**Root cause:** the Maestro ambush fires `server.spawner.spawn_entity(room_id, room.entity_spawns[0].template)` without checking `_count_template_in_room` (`src/fablestar/maestro/modules.py:35-44`). Only `EntitySpawnManager._check_spawns` enforces the cap. Agents spend all day walking healthy through spawn rooms, so ambushes keep stacking. Ambush also announces a *neutral* bird as `…lunges into the open!`.

**Suggested fix (proposal):** make the ambush respect `max_count`, e.g. reuse `_count_template_in_room`, and skip neutral templates. Decide whether Maestro should target agents at all.

---

### QA-07 — S2 — Forge inject writes invalid YAML into live content

**Repro:** `POST /forge/inject` with `{"id": "test_isle:qa_junk_room", "yaml_content": "id: [broken"}`

**Expected:** 400 with a parse error, and no file written.

**Actual:** `HTTP 200 {"status":"success","path":"content\\world\\zones\\test_isle\\rooms\\qa_junk_room.yaml"}`. The file existed on disk and HotReloader picked it up. It was deleted after the test.

**Suggested fix (proposal):** `yaml.safe_load` plus `RoomModel.model_validate` before the atomic write, and check that `id` matches the target, the same way the persona PUT already rejects `invalid_persona`.

---

### QA-08 — S3 — Admin `give` accepts a huge negative Digi value

**Repro:** `POST /admin/agents/tessa_moke/give` with `{"stat": "digi", "value": -999999}`

**Expected:** 400, or a clamp to ≥ 0.

**Actual:** `HTTP 200 {"status":"ok","stat":"digi","value":-999999}`. Tessa's wallet read back as `-999999` and was restored to 6 afterwards.

**Suggested fix:** validate `value >= 0` for wallet stats in the route. Staff-only, so S3.

---

### QA-09 — S3 — 5000-char username returns HTTP 500 — FIXED

**Repro:** `POST /play/auth/register` with `{"username": "Q"*5000, "password": "qa-pass-9x"}`

**Before:** `HTTP 500 "Internal Server Error"`. `accounts.username` is `String(50)` and the service never checked the length.

**After:** `HTTP 200 {"ok":false,"error":"username_too_long"}`, verified live after restart.

**Fix applied:** `services/player_service.py` returns `username_too_long` when the length is over 50. One file, one guard.

---

### QA-10 — S3 — "The scene:" narration is late, stale, and contradicts content

**Repro:** walk `north` from the ferry landing to the harbor docks.

**Actual**
- The move prints Harbor Docks, then `The scene: The weathered ferry ramp juts into grey harbor water…`, which describes the *previous* room.
- Scenes also trail unrelated commands: `''`, `'"'`, `attack`, `give`, `missions accept nobody`, `xyzzy`.
- `drone_gulch` narration invents "eternal night… pale, unchanging stars" while the room's own ambient says `The wreck ticks in the sun like a slow clock.`
- One pawn-shop scene describes the South Road.

**Root cause:** `commands/info.py:36` hardcodes `{"time_of_day": "Eternal Night"}`. The scene task is fire-and-forget with no staleness check against the player's location when it completes, and it runs on every auto-look.

**Suggested fix (proposal):**
- Drop the scene if the player has moved since the request.
- Pass the real time of day.
- Rate-limit to first visit, or explicit `look` only.

---

### QA-11 — S3 — No arrival or departure messages

**Repro:** the watcher and tester stand in the ferry landing; the tester goes `north` then `south`.

**Expected:** the watcher sees `Qa Tester leaves north.` and `Qa Tester arrives from the north.`

**Actual:** the watcher saw nothing (empty capture).

**Suggested fix:** broadcast leave and arrive lines in `commands/movement.py` to `get_room_players` of the old and new rooms, excluding the mover. Agents already read perception lines, so they benefit too.

---

### QA-12 — S3 — `look <target>` ignores its argument

**Repro:** `look sign`, `look north`, `look Qa Watcher`, `look at sign`, `look in chest`

**Expected:** a feature, exit, or player description, or `You see no 'sign' here.`

**Actual:** all five print the full room. `examine sign` works (`WELCOME TO TIDEGATE ISLE. Beneath the official paint…`). `examine Qa Watcher` gives `You see nothing notable called 'qa watcher'. Worth a look: tide-stained welcome sign.`

**Suggested fix:** when `look` has args, delegate to `examine`. Strip leading `at` and `in`. Teach `examine` about players and exits.

---

### QA-13 — S3 — No input length cap, no flood throttle, raw ANSI relay

**Repro and actual**
- `say` + 10,000 × `A` is broadcast in full to the room.
- `x` × 10,000 gives `Unknown command: 'xxxx…'`, echoing all 10k characters back.
- 500 separate `who` frames in 8 s gave 500 replies with no throttle and no disconnect.
- `say \x1b[31mred ansi\x1b[0m`: the watcher's raw frame is `'Qa Tester says: "\x1b[31mred ansi\x1b[0m"\r\n'`. A telnet-style client would render colour or cursor control from another player's text.

**Safe:** 500 `look`s joined by newlines in one frame collapse into a single command, which is not an amplification vector.

**Suggested fix (proposal):**
- Cap an inbound frame at about 512 chars in the protocol.
- Truncate the echo in the unknown-command reply.
- Use a per-session token bucket, e.g. 10 commands per second.
- Strip C0 control characters except `\t` from player-supplied text.

---

### QA-14 — S3 — Reserved and confusing names allowed

**Repro:** create characters named `admin`, `north`, `look`, and `Qa-`. All returned `ok=True`.

**Impact:** `tell north …` is ambiguous and `admin` can impersonate staff. A name ending in `-` passes the regex.

**Suggested fix:** a reserved-word list covering command verbs, aliases, directions, `admin`/`staff`/`gm`/`system`, and agent names (see QA-01). Require that a name starts and ends with a letter.

---

### QA-15 — S3 — Password rules inconsistent

**Actual:** the API `PlayAuthBody.password` has `min_length=8` (`HTTP 422 … "String should have at least 8 characters"`), while `PlayerService.register` checks `len(password) < 4`. Non-API callers of the service (scripts, tests) accept 4-character passwords.

**Suggested fix:** one constant used by both. Not changed, because picking the number is a policy call.

---

### QA-16 — S3 — Player client: scroll, completion, unbounded log

**Code read only.** Browser checks were not driven; see Coverage.
- `player-ui/src/mud/03-narrative.jsx:914`: `scrollTop = scrollHeight` runs on every `lines` change. A player reading scrollback is pulled to the bottom by every ambient line, agent say, or late scene narration, and the island is busy with 8 agents. Fix: only auto-scroll when the view was already near the bottom.
- `03-narrative.jsx:1341`: the Tab-completion `CMDS` list offers commands that don't exist (`inscribe`, `cast`, `get`, `glyphs`, `delve`, `quest`, `journal`, `keybinds`, `triggers`, `config`). It lacks real ones (`browse`, `buy`, `sell`, `craft`, `missions`, `rent`, `wallet`, `flee`, `emote`). Fix: fetch the list from the server's `help` registry.
- `App.jsx`: `chatMessages` is capped with `.slice(-99)`, but `narrativeLines` appends forever (`setNarrativeLines((prev) => [...prev, …])`). A long session grows the DOM without bound.

---

### QA-17 — S4 — `flee` with nothing hostile

**Repro:** in `test_isle:town_plaza` with no entities, run `flee`.

**Actual:** `You flee south!` and the player moves.

**Suggested:** `There's nothing to flee from.` when no hostile is in the room.

### QA-18 — S4 — `map` lists every unexplored room

**Actual:** `map` on a new character prints 31 `[?] unexplored` lines around two known rooms.

**Suggested:** collapse to `+29 unexplored` or omit.

### QA-19 — S4 — First screen has no help hint

**Actual:** a new character sees only the Ferry Landing room block.

**Suggested:** a one-time line: `New here? Type 'help' for commands.`

---

## Fixes applied (trivial, one file each)

| Change | File | Verified |
|---|---|---|
| `username_too_long` guard (QA-09) | `src/fablestar/services/player_service.py` | live: 500 became `{"ok":false,"error":"username_too_long"}` |
| `k` alias for `attack` | `src/fablestar/commands/combat.py` | no alias conflict (grep) |
| `logout` alias for `quit` | `src/fablestar/commands/admin.py` | no alias conflict (grep) |

Ruff clean; `pytest` 284 passed.

## Missing conventions

Expected by MUD players, absent today:

- **Unique-prefix command matching:** `sc`, `wh`, `eq`, `hel`, and `invent` all give `Unknown command`. `inv` works only because it is an explicit alias.
- **Did-you-mean** for typos: `lok`, `inventroy`, `atack drone`, `hlep`.
- **Missing commands:**
  - `go <direction>`
  - `exits`
  - `give <item> to <player>`
  - `put <item> in <container>`
  - `shout`
  - A way to transfer Digi (`give 5 digi to …` and `pay …` are both unknown).
- **`look <thing>` / `look at <thing>`:** see QA-12.
- **Arrival and departure lines:** see QA-11.
- **Command chaining or repeat:** no `;` separator and no `!` repeat. The `look && who` input ran `look` and silently dropped the rest.

## Design smells (not defects)

- **Faction standing on mob kills is surprising:** killing a feral scrap drone printed `Your standing with Salvage Union worsens: you are now disliked.` Nothing in the room or the drone suggests that faction cares.
- **Proficiency lock count isn't limited:** three leaves locked with no cap message (`Leaves — raise: 275 lower: 0 lock: 3`). Unclear whether the design intends a limit.
- **Pawn spread:** the pawn shop pays 2 Digi for a sealed ration pack and immediately shelves it at 5. This is intended economics, but it is steep for new players selling their first loot.
- **Agents appear in `who` as ordinary players:** intended parity, but combined with QA-01 a player can't tell a real person from an agent.

## Known issues — verification

| # | Issue | Status |
|---|---|---|
| KI1 | Dispatcher singleton | **Fixed.** A single `CommandDispatcher` is owned by the server (`server.py`); commands reach it through `app_instance`. |
| KI2 | Ghost players on disconnect | **Fixed for clean disconnects.** The room set went `['Qa Tester', 'Qa Watcher']` then `['Qa Watcher']`. **Regressed on double login:** see QA-02. |
| KI3 | Broken imports in communication commands | **Fixed.** `say`, `emote`, `tell`, and `who` all work; hot reload of the module works. |
| KI4 | Multi-message frames mis-parsed by client | **Not reproduced.** The server sends one message per frame. The client `JSON.parse`s a whole frame and falls back to line-splitting raw text. |

## Coverage

**Exercised:** onboarding (Pass 1), parser abuse (Pass 2), world, movement, and multiplayer (Pass 3), systems (Pass 4: proficiencies, items, shops, currency, rent, combat), admin and hot reload (Pass 6).

**Not covered, or partial:**
- **Pass 5 browser checks were not driven:** command history, double-Enter, rapid click, focus return, narrow width, reconnect banner. Logging into the player UI means typing a password into the page, which this agent doesn't do. Client findings (QA-16) come from reading code. A human should spend five minutes on those checks.
- **Death and acting while dead:** the tester never died (the drones hit for 5 and the loop ended at 40 attacks), so the death, respawn, and item-loss path is untested this pass.
- **Starter allocation with float or bool values:** blocked by `character_limit` (8 characters per account) before validation ran. It still needs a run on a fresh account.
- **`exit` and `logout`:** not reached, because `quit` closed the socket first. `exit` exists as an alias and `logout` was added.
- **Glyph runtime:** no glyph commands exist server-side (the client still advertises `inscribe`, `cast`, and `glyphs`).
- **PvP:** `attack Qa Watcher` gives `You see no 'qa watcher' here to attack.` Consistent with no PvP, but no design doc was found to confirm it.
- **Crafting and deconstruction, missions accept/complete, rent success path:** only error paths were probed this pass; the success paths were exercised by agents during the overnight soak (see `SOAK_2026-09-13.md`).

**Test data cleanup:**
- Deleted the QA accounts `qa311002` and `qw311183` with all nine characters, and removed their Redis keys and room-set entries.
- Deleted the junk forge room file.
- Restored Tessa's wallet.
- Restarted the server, and agent Sela re-registered.
