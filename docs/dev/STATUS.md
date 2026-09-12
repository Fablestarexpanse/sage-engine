# Project Status — updated 2026-09-12

One page: what's done, what's next. Update this when a milestone lands.

## Health scores (desloppify)

| Project | Strict score | Target | State |
|---|---|---|---|
| Server (`src/fablestar`) | **85.6** | 85 | ✅ target met (merged in PR #2) |
| WorldForge (`worldforge/`) | **85.9** | 85 | ✅ target met (merged in PR #3) |

Test suites: server **150** pytest, WorldForge **34** vitest — all green.

## Done (crossed off)

### Engine / server
- [x] Deterministic 4 Hz engine, Redis hot state, Postgres persistence, hot reload
- [x] Conduit proficiency system (dot-path trees, five stats, chargen picker)
- [x] Admin security: staff JWT, rate limits, CORS, first-message WS auth envelope
- [x] Play session tokens (password not re-sent per action)
- [x] Service architecture (economy/player/scene services, six admin routers)
- [x] Explicit LLM failure contract (`LLMGenerationError`); narration fallbacks intact
- [x] Per-entity combat locking; optimistic-concurrency 409 guard incl. deletes
- [x] Atomic writes on every content writer (server, TOML persist, worldforge-mcp, Tauri bridge)
- [x] Test foundation: admin HTTP layer, durability write, economy, staff guards,
      moderation endpoints, combat narration branches (M1 milestone closed)

### Admin console
- [x] Audit + all 8 recommended fixes: Content Library nav consolidation, live
      error banners with auto-recovery, real spawn/despawn, conflict guards

### WorldForge
- [x] Multi-floor system (floor switcher, ghost nodes, stair links, DoorPorts)
- [x] Startup root auto-detection + `WORLDFORGE_ROOT` + scaffold prompt
- [x] Live watch (guarded), zone delete UI
- [x] Full audit (`WORLDFORGE_AUDIT.md`) + health pass: no silent data loss
      (dirty guards, write-first saves, draft-clobber fix), hardened Rust
      bridge (atomic + traversal guard + CSP), store-owned persistence,
      ZoneEditor 2731→2334 / RoomPanel 1218→640 decomposition, vitest suite
- [x] worldforge-mcp: `create_room` crash fixed, `reference_image` preserved,
      exit-write dedupe, documented as third content writer

### AI pipeline
- [x] ComfyUI portraits + scene art with credit economy, gallery, admin costs
- [x] LM Studio / Ollama narration with deterministic fallbacks

## Needs doing

### Player-UI wiring (from 2026-09-12 live playtest — panels are still mockups)
- [x] Wire side panels to server state: character_snapshot now pushed after every
      command + effect tick (location/effects/inventory added); LOCATION, VITALS,
      INVENTORY, EFFECTS render live server state (verified in client + ws probe).
      Still fake: MAP / GLYPH LOADOUT / COMMS placeholders
- [ ] Remove the demo "Corroded Junction" intro block pinned above the real narrative log
- [ ] Disconnect UX: after a server restart the dead websocket silently swallows
      commands — needs a "connection lost" banner + auto-reconnect
- [ ] Command input: rapid submits pool letters into the buffer and a later Enter
      submits the concatenation ("swsenwseachievements") — clear-on-send / queue sends
- [ ] `examine` should match room feature names/keywords more leniently (aipub bar
      features unmatched by "examine bar"); help could list aliases

### Near-term (small)
- [ ] **README screenshots** — capture `docs/screenshots/player-client.png` and
      `worldforge-map-tool.png` (instructions in `docs/screenshots/README.md`)
- [ ] worldforge-mcp `zone.yaml` shape alignment with the app scaffold
      (neither currently satisfies `ZoneModel`'s required `description`)
- [ ] `validate_zone` MCP tool (port the app's Validate-panel checks so
      LLM-drafted zones catch bad entity/item/glyph references)

### Next structural tasks (each is one focused session)
- [ ] WorldForge `rebuildGraph` split (~289 lines, five responsibilities —
      plan-recorded skip)
- [ ] WorldForge jsdom/React-Flow test harness for ZoneEditor component tests
- [ ] Server proficiencies typing pass (`dict[str, Any]` → TypedDicts) — wants
      mypy installed first
- [ ] admin-ui `App.jsx` extraction (~3.4k lines → per-page components,
      following the existing PlayerAccountsTab pattern)
- [ ] `content_browser.py` package split (deferred as not-yet-friction)

### Game content / product (the actual game)
- [ ] Flip `proficiency_combat_hybrid = false` once all 12 combat domains have
      leaf coverage, then delete the legacy stat path (pre-1.0 milestone)
- [ ] Build out real zones/content (starter_zone currently minimal after
      test-content cleanup)

Epitaph-derived roadmap (design + priorities in `docs/design/EPITAPH_LESSONS.md`):
- [x] Achievements system — YAML criteria counters, tiers, counters in player stats blob;
      `achievements` command, kill + unique-room hooks, 3 starter achievements (10 tests)
- [x] Room chats / ambient events — `ambient:` block on rooms (lines + intervals),
      AmbientManager on tick loop, occupied rooms only, no immediate repeats (7 tests)
- [x] Effects framework — dot/hot/flag effects with merge/expiry/survive-death,
      EffectsManager tick processing, `effects` command; room hazards now apply
      DoT on entry with `hazard_resist` proficiency checks (13 tests)
- [x] Search/scavenge profiles — `search:` block on features (item pool, shared
      per-window find cap via Redis TTL), `search` command with anomaly_scan
      perception bonus + field gains + `scavenged` counter (7 tests)
- [ ] Faction data model — rep levels, encounter behaviour, teaching, shop stock (medium)
- [ ] Missions vs quests split — template faction missions + hand-crafted puzzle quests, `questsense` hints (medium, after factions)
- [ ] Maestro-style event director — player-scored random events, LLM-narrated (medium-large, after effects)
- [ ] Feature-density check in WorldForge Validate / `validate_zone` (small)
- [ ] UX niceties parked from the audit: redo, delete-key, bulk multi-select
      actions, keyboard-shortcut discoverability

### Accepted risks (documented, deliberately not doing now)
- WorldForge/mcp direct-disk writes have no mtime/permission guard —
  single-operator tool, three-writer model documented in CLAUDE.md
- No live-Postgres integration test in the default suite (CI-gated future)

## Pointers
- Health tooling state: `.desloppify/` (server), `worldforge/.desloppify/`
- Audit: `docs/dev/WORLDFORGE_AUDIT.md` · Architecture: `docs/architecture.md`
- Dev standards / workflow: `docs/dev/STANDARDS.md`, `docs/dev/WORKFLOW.md`
