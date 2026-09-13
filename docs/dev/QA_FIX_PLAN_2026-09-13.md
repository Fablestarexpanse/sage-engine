# QA fix plan — 2026-09-13

Source: `QA_PLAYTEST_2026-09-13.md`. Work top-down; each step = fix + test + commit.

NEXT: step 1

| Step | IDs | Fix | Status |
|---|---|---|---|
| 1 | QA-02 | Session teardown only cleans room/sync when this session still owns the player | todo |
| 2 | QA-01, QA-14 | Character names: case-insensitive unique, not an agent name, not reserved; kick_existing never evicts an agent | todo |
| 3 | QA-03 | Combat: send deterministic line immediately, narration as background flavour | todo |
| 4 | QA-06 | Maestro ambush respects max_count, skips neutral templates | todo |
| 5 | QA-07 | Forge inject validates YAML + RoomModel + id match before writing | todo |
| 6 | QA-04 | Dispatcher keeps raw-case args for free-text commands (say/emote/tell) | todo |
| 7 | QA-05 | tell: longest online-name prefix match, excludes sender, ambiguity message | todo |
| 8 | QA-13 | Inbound frame cap, truncated unknown-command echo, per-session rate limit, strip control chars | todo |
| 9 | QA-10 | Scene narration dropped if player moved; no hardcoded Eternal Night | todo |
| 10 | QA-11 | Arrival/departure broadcasts | todo |
| 11 | QA-12 | look <target> delegates to examine; examine players | todo |
| 12 | QA-08, QA-15, QA-17, QA-18, QA-19 | Admin give clamps wallet ≥0; one password minimum; flee needs a hostile; map collapses unexplored; first-screen help hint | todo |
| 13 | QA-16 | Player client: scroll only when at bottom, cap narrative lines, completion list from real commands | todo |
