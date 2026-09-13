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
- Death / respawn path still untested by QA.
- Chargen float/bool starter allocation still untested.
- Tab completion list is static; drifts when commands are added (a server-provided list would fix that).
