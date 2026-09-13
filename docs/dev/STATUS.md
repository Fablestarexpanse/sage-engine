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

### Tidegate Isle era (2026-09-12: starter_zone deleted, owner call)
- [x] Agents = computer-controlled players: conduit proficiency block seeded at
      spawn (same leveling engine), counters tracked (kills, deaths,
      goals_completed, items_used + per-template for "most used item");
      agents Lv + K/D in the admin watch table, full metrics in the detail
      drawer. Agents excluded from admin player/session lists and counts
      (Agents tab is their home; in-world they remain players)
- [x] Agents tab data views: detail drawer shows inventory with equipped
      slots, a skill sheet (FRT/RFX/ACU/RSV/PRS + proficiency leaves), and
      metrics; new Stat board view — per-agent levels/kills/deaths/goals/
      items-used/most-used/top-prey/rooms/achievements/memories with an
      all-agents totals row; unknown future counters (trades, rent, ...)
      grow columns automatically from the counters blob
- [x] XP progression: 60s time-series samples (levels/kills/goals/rooms) in
      the stats blob (cap 400 ≈ 6.5h, durable), multi-line chart in the
      detail drawer. FINDING: field proficiency gains are dead for everyone —
      try_field_gain hits depth_gate (tier-3 leaf needs parent branch >= 15,
      no in-game path raises branches); 68 kills = 0 levels. Owner decision
      in docs/design/AGENT_LIFE_ROADMAP.md item 9
- [x] 5 new islander agents (8 total): Aldo Vex (pawnbroker), Meri Harrow
      (storekeeper), Old Pell (fisherman), Juno Task (orchard/forager),
      Cutter Vale (lighthouse salvage scout) — routines match their trades
- [x] docs/design/AGENT_LIFE_ROADMAP.md — gap analysis for agents living
      full lives (money, shops, hunger, rent, work, society, day cycle,
      death costs) with build order E1-E3
- [x] Tidegate Isle (test_isle, 26 rooms): harbor/ferry arrival, town plaza,
      market with 4 shops (general store, pawn/salvage, apothecary,
      chandlery), clinic (safe respawn), orchard/meadow/forest, drone gulch +
      scrap beach + tide caves (hostiles/salvage/radiation), lighthouse with
      floor-1 lamp room. Cross-zone: town_plaza west <-> aipub:pub_entrance
      (the AIpub, with apartments upstairs for rent/living tests). Density
      1.92, validate_zone clean. START_ROOM/RESPAWN_ROOM constants in
      world/defaults.py; characters saved in deleted rooms auto-relocate
- [x] World Builder: Export PNG button renders the whole zone graph
      (html-to-image over the React Flow viewport)
- [x] E1 survival economy: digi wallet in the stats blob for everyone
      (players seeded from digi_balance and mirrored back on flush; agents
      seeded from persona `digi`, durable); shop blocks on room YAML
      (general store, pawn & salvage [buys 50%], apothecary, chandlery
      [buys 35%], the AIpub bar w/ algae stout); browse/buy/sell/wallet
      commands; trades/purchases/sales counters; clinic bill (10 Digi, to
      zero) on player and agent respawn; agents: sell/buy intent goals +
      deterministic sell-when-in-buying-shop Body reflex. Verified live:
      player bought a stout at the AIpub (100→96), sold it at Aldo's,
      bought a blade (→73); Sela sold 2 power cells on her own (20→32
      Digi, trades 2)
- [x] Character redo (owner call): every persona now rolls its own conduit
      attribute spread + starting wallet (persona `attributes` + `digi`);
      all 8 restarted with distinct sheets (Aldo PRS 15 / 120 Digi,
      Pell RSV 15 / 15 Digi, ...)
- [x] E2: hunger need (rises ~20min; eating settles it; Body eats when
      hungry); rent command at the AIpub bar (15 Digi, 2 apartments, Redis
      rentals hash + home_room; own-bed sleep restores more); 40-min world
      day cycle; deterministic life goals (starving→buy food, homeless+40
      Digi→rent, exhausted→sleep at home, evening pub drift), throttled
      2min. Verified: Aldo + Meri rented unprompted; full pub refuses
- [x] E3a: budgeted agent-to-agent pub talk — an idle agent in the AIpub may
      open ONE exchange with another agent (5min/agent + 10min/pair
      cooldowns, one reply via pending-key, replies never re-trigger).
      Verified live: Juno opened on Old Pell; Pell answered with a weather
      report, exactly one exchange
- [x] Shops admin tab: every shop room with keeper (live wallet, current
      room, home, carried goods), stock + prices + buy policy, and a
      per-shop transaction ledger (Redis capped list written by buy/sell)
      with sold/bought totals. shop.owner links a persona id; Meri owns
      the general store, Aldo the pawn shop
- [x] E3b: faction missions as agent work — missions pay Digi now
      (FactionModel.mission_pay; dockworkers 15, salvage union 10); life
      goals: purpose > 0.8 with no contract → `missions accept`, active
      kill contract → walk to the target's spawn room (fight reflex + the
      combat mission hook finish it), active collect contract → walk to a
      room whose search profiles yield the item and search, deliver when
      carrying enough. Keeper tills: sales pay into the owner-agent's
      wallet, buy-backs draw from it (floored at 0, skipped for
      self-trades). Verified live: Brant and Old Pell both took
      dockworker kill contracts and marched on the drone gulch; Juno
      completed a mission and banked the pay
- [x] Depth-gate bootstrap (owner said continue; smallest-change option):
      a field gain blocked by the branch-investment gate now trains the
      deepest ungated ANCESTOR instead — combat rises to 10, opening
      combat.melee, which rises to 15, opening the leaves; fundamentals
      never train past the next gate. Investment rule preserved; agent
      Levels metric counts branch levels so bootstrap progress shows.
      Verified live: Aldo Vex earned the world's first level (traversal 1)
      by walking his errands. Revisit if you want option (b)/(c) instead

- [x] World fleshing pass (owner ask): sci-fi arsenal — pulse pistol
      (ammo-fed: consumes a charge_cell per shot, dry weapon adds nothing,
      "clicks empty"), shock baton, scrap plate armor; food variety
      (kelp bread, dried gullwing, stim shot); drop materials (drone core,
      crab chitin, hound pelt, the Warden's lens). New mobs: grey gullwing
      (neutral — ignores you unless you start it), razor crab + rust hound
      (aggro), and the Cave Warden — a 60-hp boss construct guarding the
      tide caves' humming thing, dropping its lens. Spawns across meadow/
      shore/beach/forest/pier/orchard/caves; chandlery sells the arsenal,
      grocers the food; factions hire against the new fauna (dockworkers:
      hounds + crabs; union wants drone cores + chitin). Density 2.23.
      Verified live: bought pistol + one cell (broke after), first shot
      hit for 10, "That was your last charge cell", follow-ups clicked
      empty at fist damage; two crabs killed, both dropped chitin;
      gullwings coexisted peacefully; the Warden spawned in the caves

- [x] Crafting + deconstruction (owner ask): recipes on ItemTemplate
      (recipe inputs, yields batch size, scraps outputs) — recipes/craft/
      deconstruct commands; equipped gear never counts as parts; crafting
      trains the fabrication tree, deconstruct trains salvage.disassembly;
      crafted/deconstructed counters. Recipes: charge cells 3-from-a-power-
      cell, scrap blade, shock baton, scrap plate (3 chitin), pulse pistol;
      warden lens + drone core deconstruct-only. Drop RATES (owner ask):
      loot is now a drop table ({template, chance, count}; bare ids keep
      legacy 60%) — drone 50% cell/15% core, gullwing 70%, crab 55%,
      hound 65%, Warden 100% lens + 4 cells + 80% core. Verified live:
      'charge cell x3' from one dead cell, plate from 3 chitin, strip
      plate back to chitin, equipped pistol refused

### worldforge-mcp gaps found building Tidegate Isle
- [ ] create_room(from_room, from_dir) positions the room but does NOT create
      the exit — every link needs a separate connect_rooms call; either add
      link=True or document loudly
- [ ] No collision check: two rooms can land on the same canvas x/y silently
      (hit twice; had to set_room_position manually)
- [ ] No MCP way to write features/search profiles, entity_spawns, hazards, or
      ambient blocks — gameplay content still needs direct YAML edits
- [ ] No cross-zone exit tool (set_exit is same-zone only) — AIpub link was a
      manual YAML edit
- [ ] No delete_zone / rename_zone tool (starter_zone removal was rm -rf)

### Player-UI wiring (from 2026-09-12 live playtest — panels are still mockups)
- [x] Wire side panels to server state: character_snapshot now pushed after every
      command + effect tick (location/effects/inventory added); LOCATION, VITALS,
      INVENTORY, EFFECTS render live server state (verified in client + ws probe).
      Still fake: MAP / GLYPH LOADOUT / COMMS placeholders
- [x] Demo "Corroded Junction" intro block removed — DEFAULT_NARRATIVE is just
      the connect line; log opens with the real room (verified live)
- [x] Disconnect UX: "Connection to the station lost — reconnecting…" banner +
      2.5s auto-reconnect (verified live: kill server → banner, restart → clears)
- [x] `examine` dead ends now list the room's examinable features (or say nothing
      rewards a look); help lists aliases ("attack (a, kill, hit)")
- Command-input letter pooling: could not reproduce with a real keyboard — the
      "swsenwseachievements" artifact came from automation typing into an
      unfocused page; CommandInput already clears on send. Watch for it in play

### Near-term (small)
- [ ] **README screenshots** — capture `docs/screenshots/player-client.png` and
      `worldforge-map-tool.png` (instructions in `docs/screenshots/README.md`)
- [x] worldforge-mcp `zone.yaml` shape alignment: create_zone always writes
      id/name/description/depth_range (ZoneModel shape); app scaffold's
      starter zone.yaml gains the same fields
- [x] `validate_zone` MCP tool: ports the app Validate panel to Python —
      descriptions, broken/self/asymmetric exits (one_way honoured),
      orphans/disconnected, depth jumps, unknown entity templates, loot→item
      refs, glyph prerequisites, feature density. Verified: starter_zone
      clean (density 1.50), aipub flags 2 broken exits to deleted rooms

### Next structural tasks (each is one focused session)
- [ ] WorldForge `rebuildGraph` split (~289 lines, five responsibilities —
      plan-recorded skip)
- [ ] WorldForge jsdom/React-Flow test harness for ZoneEditor component tests
- [ ] Server proficiencies typing pass (`dict[str, Any]` → TypedDicts) — wants
      mypy installed first
- [x] admin-ui `App.jsx` extraction: 3426 → 451 lines. adminCommon.jsx
      (constants, ws helpers, icons, UI atoms, usePolledList) + src/pages/
      {AiForge,Dashboard,Players,ContentLibrary,Server,Operations,StaffTeam}Page.
      Build clean, every page click-verified live
- [ ] `content_browser.py` package split (deferred as not-yet-friction)

### Agent NPCs (headless players — plan: .claude/plans, 2026-09-12)
- [x] M1 bodies: AgentSession (Session + NullProtocol, dispatcher-only actions),
      Body reflexes (flee/fight/eat/rest/goal/wander w/ BFS routing), 3 personas
      in content/agents/*.yaml; ghost-room + look-players prerequisite fixes
- [x] M2 feelings + admin: deterministic mood/needs/bonds w/ baseline decay;
      /admin/agents API (list/detail/POV/restart/enable/teleport/give/persona
      GET+PUT) + Agents tab in admin-ui (watch table, drawer, YAML editor)
- [x] M3 voice: separate agents_llm.toml endpoint + own circuit breaker;
      reply gate (addressed by non-agent, 20s cooldown), sanitizer; degrade
      verified live (dead endpoint → '[no reply]' in POV, body unaffected).
      Positive path awaits a real local model in config/agents_llm.toml
- [x] Embedded brain backend + admin controls: llama-cpp-python in-process GGUF
      inference (EmbeddedLLM, same generate_or_raise contract + own breaker;
      optional dep `agents-embedded`); backend selectable lm_studio/ollama/
      embedded from the Agents tab Brain panel (enable toggle, model path/URL,
      one-shot "Test brain"); settings persist to config/agents_llm.toml and
      apply live (AgentBrain.reconfigure). Verified live: backend switch saved,
      test returns graceful "model file not found" with no GGUF present.
      Positive path verified with Qwen2.5-3B-Instruct-Q4_K_M.gguf (~1.9 GB in
      models/, gitignored): admin Test brain ✓ 2.16s; live in-game reply
      ('Sela Varn says: "anythin needs doin?"' to an addressed say). M3 fully
      closed; no external LLM process needed for agent voices
- [x] M4 intent: when idle near a real player (90s/agent cooldown, one
      generation in flight), the brain answers a JSON goal
      (wander_to/hunt/rest/talk/scavenge/idle) parsed strictly and compiled
      to a Body command script (BFS route_path for wander_to/hunt); memory
      ring (agent_memories in stats blob, cap 40) feeds intent + voice
      prompts and records decisions/completions; POV logs real intent
      prompts. Verified live with embedded Qwen: Sela chose
      '{"goal":"scavenge","why":"Find food to replenish health"}' → search
      executed, goal cleared
- [x] Durability: agent_state table (Alembic k4l5m6n7o8p9), flushed on the
      60s persistence cadence; spawn restores stats/inventory/room, admin
      Restart = reset-to-persona (row deleted). Verified: [restored] spawns
      at drifted rooms after server restart
- Phase 2 (explicitly later): pgvector memories + reflection, bonds→long goals,
      trading, LOD scheduler for dozens+, world chronicle feed

### Game content / product (the actual game)
- [x] Player command surface v1 complete (2026-09-12 audit): use/eat, rest
      (safe-room heal-over-time), who, tell, emote, equip/unequip with
      weapon/armor slots feeding combat bonuses; canonical hp/max_hp seeded
      at bootstrap. Two gear items in the alcove search pool. (8 equip tests)
- [ ] Glyph runtime (cast/inscribe) — glyph content exists, no engine yet
- [x] Comms panel backed by real chat: say/tell emit chat_message client
      notices (agents excluded), panel shows Local + Tells with a working
      send box (say / tell passthrough); fake party roster removed — party
      system itself is still future work. Verified live in browser + ws
      (agent reply lands in Local). Map panel real too: zone rooms/edges
      from editor positions in character_snapshot.map, visited tracking,
      current-room marker follows moves
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
- [x] Faction data model v1 — content/factions/*.yaml, per-player rep in stats blob,
      kill penalties (own faction) + kill rewards (enemies list), standing-crossing
      announcements, `factions` command; 2 dock factions live (8 tests). Deferred:
      teaching, shops, encounter behaviour (need NPC AI / shop systems first)
- [x] Faction missions (missions half of the split) — generated kill/collect
      contracts from faction config, one active, kill progress in combat,
      collect turn-in consumes inventory, mission_rep + missions_completed
      counter + Contractor achievement; `missions` command (10 tests).
      Hand-crafted puzzle quests + `questsense`: deliberately NOT planned for
      now (owner call 2026-09-12) — missions cover advancement; revisit post-1.0
- [x] Maestro event director — 30s consideration windows, per-player cooldowns,
      roulette over module interests with heavy do-nothing weight; modules:
      ambush (spawn-capable room + healthy player), mercy (supplies when hurt),
      dread (atmosphere). Live-verified ambush + dread firings (7 tests).
      LLM-narrated variants: later, modules are the hook point
- [x] Feature-density check: in app Validate (validation.js) and the
      validate_zone MCP tool
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
