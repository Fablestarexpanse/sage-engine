# Engine Decoupling Brief — Fablestar Expanse → SAGE

> Owner brief, received 2026-09-13. Stored verbatim so it survives context loss.
> Precedence: this brief (and the Phase 1 contracts once approved) outranks code, repo docs, and
> the Obsidian vault on engine structure. Owner rulings made after this brief are in
> `docs/sage/DECISIONS.md`.

**Working engine name:** SAGE (Synthetic Agent Game Engine)
**Status:** Planning brief. Do not write refactor code until Phase 1 is approved.

---

## 1. Intent — read this part twice

This codebase was built as *Fablestar Expanse*, a single sci-fi MUD. After building this far it's clear the engine underneath is the more valuable thing. It can run any kind of world, not just this one.

The goal is to invert the relationship:

- **Today:** a Fablestar game that happens to have reusable parts.
- **Target:** a world-agnostic engine, with Fablestar Expanse as the first world package riding on top of it.

Anything that is true *only because this world is Fablestar* must move out of the engine and into a world package. That includes mechanics, content, stat definitions, currencies, AI prompts and style, progression rules, player-facing vocabulary, the login banner, the MOTD, and help text.

**The test of success is not "does Fablestar still run."** It's: *a second, deliberately different world runs on this engine with zero changes to engine code.* Build toward that test, not toward a tidy-looking diff.

The intent behind any ambiguous instruction in this document is: **if a world author would plausibly want it different, it belongs to the world, not the engine.**

---

## 2. Locked decisions — do not relitigate these

| # | Decision | Notes |
|---|---|---|
| 1 | **Pluggable mechanics**, not just data-driven config | Worlds can add real systems, not only fill in parameters. Glyphs become a plugin, not core. |
| 2 | **One world per deployment** | No `world_id` scoping on tables. *But* namespace Redis keys by world slug anyway — free now, saves a migration later. |
| 3 | **Trusted plugin model, no sandbox** | We won't host third-party worlds. Operator accepts the risk. Plugins must ship a manifest declaring what they touch, and the loader must log loudly when loading non-first-party code. |
| 4 | **Private monorepo** | `engine/` + `worlds/` + `plugins/`. Possible paid release later, so keep the seam clean enough that extraction is a `git filter-repo`, not an excavation. Audit dependency licenses early. |
| 5 | **Flexible stats** | JSONB on the character row, with the world declaring a stat schema validated on load and on write. No hardcoded five attributes. Add generated columns/indexes only for stats actually queried across players. |
| 6 | **AI layer stays, becomes configurable** | It works in beta. Do not rebuild it. Split it: *engine* keeps provider/model routing, caching, retries, queueing, cost controls. *World* owns system prompts, tone and style guide, image style tokens, LoRA references, NPC behavior priors, content rules. |
| 7 | **Full lexicon** | Every player-facing noun and string is world-supplied and live-editable from Nexus, including login banner, MOTD, and help text. |
| 8 | **Plugins may own database tables** | They ship their own migrations, with rollback on uninstall. |

---

## 3. Invariants — enforce these in CI, not by discipline

1. `engine/` never imports from `worlds/` or `plugins/`. Dependency direction is one-way, always.
2. No world-specific string literals anywhere in `engine/`. Build a denylist grep check seeded with: Fablestar, Conduit, Glyph, Glyphstream, Resonance, Digi, Pixel, Fortitude, Reflex, Acuity, Resolve, Presence.
3. Every player-facing string in engine code is a lexicon key, never a literal.
4. Engine code has no knowledge of specific stat names, currency names, or ability types.
5. Both reference worlds boot and pass smoke tests in CI.

If any of these can't be enforced mechanically, say so and propose an alternative check.

---

## 4. Decisions delegated to you

You can see the actual code; I can't hold all of it in my head. These are yours to make, but document the reasoning in the Phase 1 deliverable so I can push back.

**A. The extension point catalog.** This list *is* the engine's public API. It must be finite, and anything not on it is core engine and not pluggable. Audit what's built, then propose the final list. My starting proposal, to accept, cut, or expand:

- command verbs
- entity components
- stat and progression systems
- abilities
- combat resolution
- economy and currency
- room and content generation
- AI narrative hooks
- scheduled tick jobs
- event bus subscriptions
- client UI panels
- Nexus admin panels

**B. Hook mechanism.** Event bus, direct hook registry, or both. Your call based on what the current dispatcher and tick loop actually look like.

**C. Plugin hot-reload vs restart-on-change.** YAML hot-reload already exists. Python code reload is a different animal. Restart is the safe default; override it if the dev loop would suffer badly.

**D. Migration sequencing and schema details**, including how plugin-owned migrations interleave with core ones.

**E. The tool surface.** See Phase 5. Recommend the route for the map tool, Nexus, and WorldForge as a set, not one at a time.

**F. Anything I've missed.** If the audit turns up a category of world-specificity not covered here, raise it before designing around it.

**G. This plan itself.** Everything in section 5 was written without seeing the code. Treat the phase order as a proposal, not an instruction. If the audit says a different sequence is safer, cheaper, or less likely to leave the game unplayable for a stretch, say so and argue for it in the Phase 1 deliverable. The locked decisions in section 2 and the intent in section 1 are fixed. The route to them is not.

---

## 5. Order of work

### Phase −1: Stabilize first
Do not refactor on top of known-broken wiring. Fix these before anything else:

1. Movement and combat commands instantiate a fresh `CommandDispatcher` instead of the server singleton, breaking hot-reload. **Highest priority.**
2. `destroy_session` is missing `remove_player_from_room`, leaving ghost players in room sets.
3. The `say` command imports from the wrong module path.
4. The client only parses the first WebSocket message as JSON.

### Phase 0: Audit — no code changes
Produce an inventory of every Fablestar-specific reference in the codebase, bucketed:

- **Branding / lexicon** — strings, banners, names, help text
- **Content data** — rooms, items, NPCs, zones, lore
- **System parameters** — values that vary per world but fit the existing system shape
- **Hardcoded mechanics** — systems that exist only because this world is Fablestar
- **AI assets** — prompts, style, LoRA references, behavior priors
- **Schema** — tables and columns that assume Fablestar's model
- **Tooling** — every standalone tool and side app in or around this repo (the map tool, Nexus, WorldForge, anything else), what it currently assumes about Fablestar, and how tightly it's coupled to the game's data model
- **Documentation** — every `.md` file in the repo, plus agent-steering files (`README`, `CLAUDE.md`, `.cursorrules`, prompt docs, design specs). See section 7.

Include a rough size and risk estimate per bucket. This report tells us how big this actually is.

### Phase 1: Contracts — stop for approval before proceeding
Two specs, plus your answers to section 4:

- **World package contract** — what a world *is* as an artifact. Directory layout, manifest, version field, engine compatibility range, what it may and may not contain.
- **Plugin API spec** — extension point catalog, registration lifecycle, manifest format, migration ownership, load-order and dependency rules.

**Stop here and wait for review.** Everything downstream is mechanical once these are right and expensive to unwind if they're wrong.

### Phase 2: Scaffolding
Repo structure, the engine/world boundary, plugin loader, lexicon system, CI invariant checks. No content moved yet.

### Phase 3: Migrate Fablestar
Move Fablestar into a world package, one system at a time. The game must be playable at every commit. No big-bang rewrite.

### Phase 4: Second reference world
See section 6.

### Phase 5: Tooling

The tool surface is currently fragmented: the standalone map tool (already built), Nexus (admin UI, built), and WorldForge (specced, not built). All three overlap in what they edit. Decoupling the engine is the moment to sort that out, because all three are about to need the same thing: an editor that reads and writes world packages.

Evaluate the whole tool surface before touching any of it, and recommend a route. For each tool, the decision is one of:

- **Becomes a world-package editor** — generalized, ships with the engine
- **Folds into another tool** — its capability is absorbed, the standalone goes away
- **Stays standalone and world-agnostic** — useful on its own, reads the package format
- **Stays Fablestar-specific** — lives in the world package, not the engine
- **Deprecated** — superseded by what we're building

For the standalone map tool specifically: assess whether it should become the map/graph editing layer *inside* WorldForge rather than remaining separate. WorldForge's spec already covers zone, galaxy, and ship graph editors, which is most of what a map tool does. Building that surface twice would be a mistake, and so would throwing away working code. Look at both and tell me which way it should go.

**WorldForge isn't built yet — that's lucky.** Design it as the SAGE world-package editor from the start rather than as a Fablestar tool that gets generalized later. If the map tool's existing code can seed it, say so.

Deliverable: a short tooling recommendation as part of Phase 1, so the tool decisions are made before the contracts are frozen rather than after.

---

## 6. The second reference world — not optional

Pluggable mechanics have one specific failure mode: if Fablestar is the only world that exists while you design the extension points, every abstraction ends up shaped exactly like Fablestar, and we won't find out until we try to build world number two.

So build a small world that is deliberately *unlike* Fablestar:

- 20–40 rooms
- three attributes, not five
- a single currency
- no glyphs, no Resonance, no Glyphstream
- a different genre (modern day or low fantasy)
- a different progression model (levels, or pure skill-use, anything that isn't a 278-leaf proficiency tree)

It isn't a product. It's the test harness for the abstraction. Any seam it can't flex is a seam that isn't real yet. It also becomes the CI smoke test and the demo world if we ever sell this.

---

## 7. Documentation and direction sources

Stale docs are the biggest ongoing risk in a refactor this size. Every `.md` file in this repo is something a coding agent will read as instruction. If half of them still describe a Fablestar-only engine, work will drift back toward the old shape, session after session, and it'll look like the agent is being inconsistent when it's actually following the documents it was given.

Audit every `.md` in the repo and classify each one:

- **Agent-steering** — `README`, `CLAUDE.md`, `.cursorrules`, prompt docs, onboarding notes, the WorldForge Cursor prompt. **Highest priority.** These actively misdirect. Fix or flag them before Phase 2 begins.
- **Engine documentation** — must become world-agnostic. Rewrite as part of the phase that touches the matching code, not in one sweep.
- **World documentation** — Fablestar lore, setting, and design. Content is correct and stays correct. It relocates into the world package's own docs. Do not rewrite it.
- **Historical** — session notes, dev logs, decision records, old plans. Do not rewrite these. Add a header marking them historical and naming what superseded them. Rewriting history destroys the reasoning trail.
- **Contradictory** — anything that conflicts with this brief. Flag in the Phase 0 report. Do not silently resolve a contradiction: a conflict usually means either the doc knows something this brief doesn't, or a decision was quietly reversed. Both are worth a conversation.

**Precedence order**, for resolving conflicting direction:

1. This brief, and the Phase 1 contracts once approved
2. Current code behavior
3. Repo documentation
4. The Obsidian vault

The Obsidian vault stays canonical for **Fablestar as a world** — lore, setting, design intent. It is *not* canonical for engine architecture, and much of what it says about the engine predates this decision. When the vault and this brief disagree about engine structure, this brief wins. When they disagree about Fablestar's world content, the vault wins.

Deliverable: a documentation disposition list in the Phase 0 report — every `.md` file, its classification, and what needs to happen to it. Flag any file that would mislead a future session if left alone.

---

## 8. Rules of engagement

- When the engine/world boundary is ambiguous, **stop and ask**. Don't guess. A wrong guess buried in Phase 3 is expensive.
- Flag one-way doors explicitly before walking through them.
- Incremental over clean-sweep. Playable at every commit.
- Don't rebuild the AI layer. Make it configurable.
- Don't build extension points for hypothetical future worlds. Two worlds' worth of need is the ceiling for now.
- Prefer deleting Fablestar assumptions over parameterizing them. If a thing only Fablestar needs can be a plugin, make it a plugin.

---

## 9. Definition of done

- `engine/` contains no Fablestar references, enforced by CI.
- Fablestar Expanse runs as a world package, feature-complete against today's build.
- The second reference world runs on the same engine binary with zero engine code changes.
- Switching worlds is a config change plus a restart.
- Login banner, MOTD, currency names, stat names, and all player-facing vocabulary are editable from Nexus without touching code.
- AI prompts and style are world assets, versioned with rollback.
- A plugin can be installed and uninstalled cleanly, including its schema.
- No `.md` file in the repo still describes the engine as Fablestar-only. Historical docs are marked, not rewritten.

---

## 10. Nice-to-have, flagged for later

Prompt regressions are invisible failures — nothing errors, the world just gets subtly worse, and without version history you can't bisect it. Beyond basic versioning and rollback, two features worth building into the AI admin tooling when there's time: a preview/test-run against a sample room, and a side-by-side diff of two prompt versions.
