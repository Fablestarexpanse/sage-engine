# QA fix plan — 2026-09-13

Source: `QA_PLAYTEST_2026-09-13.md`. Work top-down; each step = fix + test + commit.

NEXT: all 13 steps done and verified live (33/33 regression checks). Open follow-ups at the bottom.

| Step | IDs | Fix | Status |
|---|---|---|---|
| 1 | QA-02 | Session teardown only cleans room/sync when this session still owns the player | done |
| 2 | QA-01, QA-14, QA-15 | Character names: case-insensitive unique (index), not an agent name, not reserved; login refuses agent-named rows; shared password minimum | done |
| 3 | QA-03 | Combat: deterministic line immediately, narration as background flavour | done |
| 4 | QA-06 | Maestro ambush respects max_count, only hostile templates | done |
| 5 | QA-07 | Room YAML writes validate YAML + RoomModel + id match | done |
| 6 | QA-04 | Dispatcher keeps raw-case args for free-text commands | done |
| 7 | QA-05 | tell: longest exact name, unique prefix, excludes sender, ambiguity list | done |
| 8 | QA-13 | Input cap 1000, control chars stripped, echo cut to 40, token bucket 8/s burst 20; prefix commands + did-you-mean | done |
| 9 | QA-10 | Scene narration: real day phase, dropped if player moved, one pending, auto-look narrates first visits only | done |
| 10 | QA-11 | Arrival/departure lines (not sent to agents) | done |
| 11 | QA-12 | look <target> delegates to examine; examine exits and players | done |
| 12 | QA-08, QA-17, QA-18, QA-19 | give refuses negative wallet/hp; flee needs a threat; map collapses unexplored; help hint | done |
| 13 | QA-16 | Client: follow output only at bottom (plus MutationObserver), cap 1500 lines, real completion list | done |
| + | — | Dev login (`dev_mode` + `dev_login`, loopback only): `POST /play/dev/login {character}` and a sign-in box | done |

## Live verification

`scratchpad/regress.py` (dev-login based) — 33/33 pass after restart. Browser (player-ui via dev login):
Enter submits, empty Enter ignored, ArrowUp history, Tab suggestions from real commands, log keeps place when
scrolled up and follows when at bottom, focus stays on the input.

## Follow-ups (not done)

- ~~Narrow screens~~ — owner ruling 2026-09-13: phones are not a supported target; tablets are. Tablet (768x1024) checked: all panels visible, no horizontal scroll, top bar a little crowded.
- Tab completion list is static; drifts when commands are added (a server-provided list would fix that).

## Death & respawn pass (2026-09-13)

Tested live (dev login, scripted + browser): combat death, affliction (DoT) death, relogin respawn, broke
respawn, inventory kept, survive_death effects kept, room set cleared on death.

Working before: disconnect on death, respawn in the clinic at half HP, 10 Digi bill (down to zero), effects
without survive_death cleared, inventory kept.

Found and fixed:
- **S2 `quit` didn't quit in the player UI** — client auto-reconnected 2.5 s after any close, including quit.
- **S2 two tabs on one character kicked each other forever** — same auto-reconnect after "signed in elsewhere".
  Server now sends `{"client_notice": "session_end", "reason": quit|died|replaced}` before closing
  (`Session.end`); the client stops on quit/replaced/refused with a banner + Reconnect button and still
  auto-reconnects after a death or a drop. The banner was hidden under the fixed top bar; moved below it.
- **S3 player deaths weren't counted** — agents counted deaths, players didn't, so the "Died Once, Billed
  Twice" achievement was unearnable; affliction deaths weren't in telemetry or the deaths heatmap either.
  Shared `effects/death.py:record_player_death` now does counter + `player_death` event + heatmap for both.
- **S3 respawn bill was silent** — wake-up text now says what the clinic took (or that you were too broke).
- **S4 DoT kept ticking on a corpse** — extra "-5 hp" line after hp hit 0; ticks stop at 0.

Design notes (not changed): death disconnects the socket and respawn happens on the next login; the web
client makes that a ~2.5 s blink. No item or XP loss beyond the 10 Digi bill.

## Chargen starter allocation pass (2026-09-13)

`POST /play/characters/create` with 30 raw-JSON allocations (dev-login token, portrait_url preset so no
ComfyUI spend; accepted characters deleted straight after).

Found and fixed (`proficiencies/starter.py:coerce_starter_level`, used by the service and the validator):
- **S2 Infinity / -Infinity / 1e400 → HTTP 500** — `int(inf)` raised OverflowError, which nothing caught.
- **S3 non-integers silently truncated** — 2.7 became 2, 5.9 became 5 (over the per-leaf max as typed),
  `true` became 1, `"3"` and `" 4 "` were accepted, -0.5 and 0.99 silently dropped. Now only ints and
  integral floats (2.0) are accepted; everything else is `invalid_starter_proficiencies`.
- **S4 duplicate keys after trimming** (`"combat.melee.blades"` and `" combat.melee.blades"`) — the last one
  silently won; now refused.

Already fine: NaN, null, lists, objects and non-numeric strings refused; 1e308 → level_out_of_range; a
non-object allocation → 422; unknown leaf at 0 is ignored; budget and per-leaf max hold. The player UI
already sends floored integers, so normal character creation is unaffected.
