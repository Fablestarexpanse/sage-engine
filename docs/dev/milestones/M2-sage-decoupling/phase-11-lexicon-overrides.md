# Phase 11: Live lexicon editing from Nexus

**Milestone:** M2 — SAGE engine decoupling
**Status:** done
**Depends on:** phase-06, phase-10
**Tags:** language=python+jsx, kind=feature, size=m

## Goal

Locked decision 7 / DoD: login banner, MOTD and every player-facing string are editable from
Nexus without touching code, versioned with rollback (contracts B.5, B.7).

## Spec (as built)

1. Core table `world_overrides` (kind, key, version, value, active, author_staff_id, note,
   created_at) — migration `n7o8p9q0r1s2`, model `WorldOverride`. No world column: one database
   per world (owner G.2).
2. `sage.lexicon.overrides.LexiconOverrides`: `active`, `history`, `save` (new active version),
   `rollback`, `clear` (history kept).
3. `SageServer.reload_lexicon_overrides()` rebuilds the lexicon with the override layer at
   startup and after every edit — no restart.
4. Nexus routes `/admin/lexicon` (list with effective value, source, package default),
   `/{key}/history`, `PUT /{key}`, `POST /{key}/rollback`, `DELETE /{key}`; tool permission
   `lexicon`; unknown keys and versions 404.
5. Admin console page "Lexicon & MOTD": searchable keys (banner/MOTD first), editor with note,
   save-and-apply, revert to package text, version history with roll back.

## Update Log

### Update — 2026-09-13 (complete)

431 passed + 9 skipped; 3 new route tests (permission, edit/rollback/revert, unknown key and
version); live 9 passed incl. override persistence against Postgres and the models-vs-migrations
check. Real run: dev DB upgraded to `n7o8p9q0r1s2` (row counts unchanged); in the admin console
the MOTD was set to "Welcome back to Tidegate Isle. The ferry runs late tonight." → a player
login showed it as the first line → "Revert to package text" → the next login had no MOTD,
history still listing v1. admin-ui builds.
