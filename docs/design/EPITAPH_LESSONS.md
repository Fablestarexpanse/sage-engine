# Epitaph Lessons — MUD design comparison and adoption roadmap

> **Flagged for owner conversation (SAGE audit §13, 2026-09-13).** This doc places ambient, search,
> effects and factions in the core engine and `RoomModel`. The SAGE brief makes world-specific
> mechanics plugins. Do not build further on this roadmap until that is resolved; see
> `docs/sage/PHASE1_CONTRACTS.md`.

Source: *The Epitaph Survival Guide* (Michael "Drakkos" Heron), the 554-page creator
handbook for Epitaph Online — a zombie-apocalypse MUD built on a Discworld-lineage LPC
mudlib. We are **not** recreating their world or theme. This document extracts what their
twenty years of MUD-building experience teaches, compares each system against Fablestar,
and turns the useful parts into a prioritized adoption roadmap.

The guide is roughly 60% LPC programming tutorial (irrelevant to our Python/YAML stack).
The valuable material is the "Being a Better Creator" design section (pp. 160–265) and
the systems quick-references (pp. 497–540, plus taskmapper pp. 80–87, effects pp. 381–390,
achievements pp. 391–402). Page numbers below cite the guide.

---

## A. Verdict summary

Ground-truthed against this repo: `src/fablestar/world/models.py` defines no quest,
achievement, faction, or rumour models (entities carry an unused `faction: "neutral"`
string); player commands are limited to admin, combat, communication, info, items,
movement, and proficiency modules.

| Area | Epitaph | Fablestar | Verdict |
|---|---|---|---|
| Engine / tooling | 1990s LPC driver, hand-edited code files, RCS source control | Deterministic 4 Hz Python engine, Redis/Postgres, hot reload, WorldForge visual editor, MCP build tools, optional LLM narration | **Ours better.** Half their book teaches builders LPC because they have no better content pipeline; our YAML + editor stack removes that entire class of work. |
| Skill advancement | Taskmapper (pp. 80–87): central task→skill mapping, use-based "TM" awards, global difficulty tiers, free vs stamina-cost checks | Conduit: dot-path proficiency trees, five stats, field/mentored/archive gains | **Concept parity; theirs is better instrumented.** Their centralized difficulty tiers (`TTSM_DIFF_*`) mean game-wide balance is one knob, and every skill check is a potential "award moment" with a visible flash message. Both ideas are worth folding into Conduit. |
| Room descriptions | Ten Commandments (pp. 215–222), craft chapter (pp. 223–231), landmark/template pipeline, day/night variants, room chats | `features[]` with keywords/descriptions; LLM colour on top | **Theirs deeper as a craft.** Their writing rules become our content standard; our LLM narration is an unfair advantage *only if* grounded by rules like theirs, otherwise it drifts into their "turned up to eleven" failure mode. |
| Quests | Hand-crafted puzzle quests, dynamic-quest doctrine (pp. 206–213), `questsense` hint command, quests-vs-missions split | None | **Gap.** |
| Achievements | Data-file driven (pp. 391–402): criteria counters via one `adjust_player_value` API, levels minor→mythic, public and spoiler-free | None | **Gap — cheapest high-value adoption.** |
| Factions | Data file per faction (pp. 529–533): rep levels, teachers, shops, random mission generator, encounter actions keyed to standing | Unused `faction` string on entity templates | **Gap.** Their key insight: factions replace classes/guilds entirely *and* give you free template missions. |
| Ambient life | Room chats, day/night text, and **Maestro** (pp. 526–528) — a random-event director that scores players by noise/visibility and fires event modules | Static rooms; entity spawns | **Gap.** Maestro maps beautifully onto our tick loop, and LLM narration could make every firing unique. |
| Status effects | Effect objects (pp. 381–390): DoT, buffs/debuffs, merge policy, death/logout persistence, skill-checked cures | Nothing generalized | **Gap.** Natural fit for Redis (`entity:effects:*`) ticked by TickManager; prerequisite for hazards, glyph effects, and boss powers. |
| Scavenging / economy | Search profiles (pp. 79–80), powered items with battery/fuel scarcity (pp. 500–503), crafting chains with material propagation (pp. 534–540) | Echo-credit art economy; item templates | **Different focus; theirs is the survival loop.** Search profiles are the small, thematic piece worth taking now. |
| Design process | Feature density metric (pp. 173–179, appendix p. 546), demographics-first planning, feature-creep discipline | Ad hoc | **Adopt the metric** — trivially computable by WorldForge's Validate panel or the planned `validate_zone` MCP tool. |

---

## B. Design principles we adopt as our own

These are the "learn from" half — process and craft rules, no code required.

1. **Interesting decisions, not randomness** (pp. 162–163, 261). Every game feature should
   present choices whose outcome is uncertain *but whose uncertainty a player can reduce by
   strategy*. Pure dice rolls are not challenge; arbitrary unsignposted death destroys
   informed decision-making entirely. Their Russian-roulette example: re-spinning the barrel
   each pull is gambling; advancing the chamber makes observation a skill.
2. **Game first, world second** (p. 260). "Realism" is never a sufficient reason for a
   mechanic. Their compulsory eating exists for three gameplay goals (scavenging need,
   anti-idle, survival tone) — realism is a side benefit. Any Fablestar system pitched
   as "more realistic" must restate its justification in gameplay terms or be dropped.
3. **Zone focus taxonomy** (pp. 164–166). Killing / wealth / questing / immersion /
   infrastructure / exploration. Every zone emphasizes two or three. Keep XP zones and
   wealth zones separate — a zone giving both obsoletes zones giving one.
4. **Demographics-first feature planning** (pp. 167–179). Before building a zone, list its
   features and rate each 1–10 per Bartle type (achiever / explorer / socialiser / killer).
   Five is "take it or leave it"; below three actively repels. The numbers are subjective —
   the *process* is what exposes weak plans.
5. **Feature density ≥ 0.5** (pp. 173–174, appendix p. 546). Features ÷ corridor rooms;
   Griffin's rule of thumb is 3–7 features per 10 street rooms. Add a corridor room only
   when you have a feature for it. Their history shows empty "we have Plans" streets stay
   empty and drag the whole game's perceived quality down.
6. **Quest commandments** (pp. 196–201). No must-have item rewards; no stat rewards;
   skill *checks* not skill *gates* (and never large levels of otherwise-useless skills);
   quests gate extra content, never core content; no lethal consequences without clear
   signposting and opt-out; findable by an averagely observant player; obvious syntax;
   obvious goal with logically discoverable steps (their Babel Fish counter-example);
   no rare-item dependencies. Accept that walkthrough sites exist — publish your own hint
   system (`questsense` + rumours) rather than punishing the honest.
7. **Dynamic over linear where it pays** (pp. 206–213). A quest whose setup randomizes per
   player can only have its *instructions* spoiled, never its *solution* (their Murder
   Mystery). But a healthy game mixes both — heavily dynamic quests all reward the same
   spreadsheet-brain skill. Rate quest rewards by randomness, player skill, character
   skill, travel, and time.
8. **Room description commandments** (pp. 215–222). Never "you" in descriptions; never
   assume the viewer's actions; no static text for dynamic objects (motion goes in ambient
   chats — their falling-acorn rule); no relative directions ("to your left"); every noun
   mentioned must be examinable; NPCs are entities, never description text; no command
   syntax in descriptions (helpfiles and in-theme signage instead); 50–80 words; sparing
   adjectives and evocative words ("peppered like a spicy herb", never turned up to
   eleven); QA by reading aloud, then re-reading days later.
9. **Descriptions at scale** (pp. 226–228). Hand-write the unique, single-describe the
   uniform, template the repeated with seeded variation. Their split: streets get one
   abstract description + proximity landmarks; unique buildings get hand-rolled rooms;
   franchise/repeated interiors are seeded templates. Ours: WorldForge stamps + LLM
   variation, grounded by rule 8.
10. **NPC classification** (pp. 232–238). Cannon fodder / service / quest / flavour / boss —
    spend writing effort where the class demands: fodder needs a description and chats,
    quest NPCs need deep drip-feed dialogue (revelations teased out across multiple asks,
    never a monologue), service NPCs need kill *disincentives* rather than invulnerability.
11. **Boss design** (pp. 244–246). Three or four *interacting* powers, designed by first
    answering "how does this boss handle an all-melee group?" and "an all-ranged group?".
    Timing imperatives (get out of range before the eruption, but someone must stay in
    melee) are what create player skill. Playtest — players will find strategies you never
    imagined.
12. **Feature-creep discipline** (pp. 250–251, 259–260). Plan conservatively, build the
    plan, extend only after shipping. Cutting an over-ambitious plan "is not an admission
    of failure." Their Death March case studies (11-year castle projects) are the warning.
    Also: complaints are not representative; complexity is not quality — simple,
    inter-related systems produce emergent depth (their one-rule smelting example).
13. **Ship it properly** (pp. 253–257). Integrate new areas with placeholders (the
    rubble-blocked street), advertise in-theme (cryptic teasers, seeded rumours — never a
    walkthrough announcement), document for other maintainers (their "Five Ws" post:
    what/who/when/why/where), and keep a personal lessons-learned file per project.

---

## C. Adoption roadmap (prioritized)

Ordered by value ÷ effort against our architecture. Items 1–8 are also mirrored in
`docs/dev/STATUS.md` so the one-pager stays authoritative.

1. **Achievements system** (small). `content/achievements/*.yaml`: criteria counters,
   level tiers minor→mythic (their XP table, p. 401), story lines rendered as
   "*Name*, in which you …". Engine mirrors their single-API design: one
   `adjust_player_value(counter, delta)` call in Redis (`player:counters:{player_id}`),
   a handler that checks thresholds on change, public announce + XP award. Their policy:
   hand out freely, but each must mean something — one achievement per subsystem beats
   five per shop.
2. **Room chats / ambient events** (small). Optional `ambient:` list on `RoomModel`
   (min/max interval + lines); TickManager emits per-room lines on a cooldown to occupants.
   Later, LLM-vary the line pool. Share pools across rooms (nine chats shared by three
   rooms beat three unique each, p. 229).
3. **Effects framework** (medium). Generalized timed effects on players/entities: classify
   (`body.bleeding`), merge policy on reapplication, expiry, per-tick callbacks,
   death/logout persistence flags, skill-checked removal — their exact API surface
   (pp. 381–390) translated to Redis + TickManager. Prerequisite for room hazards, glyph
   effects, and boss powers. Add `buffs`/`debuffs` player commands.
4. **Search/scavenge profiles** (small-medium). `search <feature>` command; per-feature
   loot profiles (keyword, item pool, per-reset limit) plus shared generic pools; a
   perception proficiency check on hidden finds with the field-gain "award moment" flash
   (their TASKER_AWARD pattern, p. 386).
5. **Faction data model** (medium). YAML factions: rep levels, initial standing,
   encounter actions keyed to standing (loathed → attack; exalted → greet), teachable
   proficiency lists with a faction-level teaching ceiling, shop stock, and rep penalties
   on killing allied NPCs via the existing `faction` field on `EntityTemplate`.
6. **Missions vs quests split** (medium, after 5). Template missions (kill/fetch/courier)
   machine-generated per faction from its `enemies`/`wanted_items` config — never
   hand-written. Hand-crafted puzzle quests reserved for uniqueness, governed by the
   commandments in section B, with a `questsense`-style hint command and quest stories.
7. **Maestro-style event director** (medium-large, after 3). A background director that
   scores each player per tick window (noise made, visibility, health, idle time) and
   roulette-selects event modules to fire — ambushes, discoveries, mercies. Our LLM
   narration makes each firing read unique; the deterministic core stays in module code.
   Potential signature feature.
8. **Feature-density check in WorldForge** (small). In the Validate panel and the planned
   `validate_zone` MCP tool: count features + spawns + hazards per corridor room and warn
   below 0.5.
9. **Cycle-variant descriptions** (small, only with a time system). `description.night`
   (or station shift-cycle) variant alongside `description.base`, plus cycle-specific
   ambient pools — only worth it once Fablestar has a clock players can perceive.
10. **Powered items** (later). Their battery/fuel scarcity loop (pp. 500–503) creates
    trade and strategic noise/light choices (the chainsaw registers an awareness event
    while running). For our starship setting this maps to power cells; defer until we
    commit to a survival-flavoured economy.

---

## D. Explicitly not adopting

- **The LPC/inheritance content pipeline.** Our YAML + hot reload + WorldForge + MCP stack
  is strictly better; nothing in their Introductory/Intermediate LPC sections applies.
- **Volunteer-organization chapters** ("Working with Others", pp. 406–495). Solo project.
- **Their world, theme, or any zombie content.** Explicit constraint of this exercise;
  only the design machinery travels.
- **Cosmetic house rules** (mandatory British spelling, double-spacing after sentences).
  We set our own style rules; the substantive writing craft from section B is what matters.
