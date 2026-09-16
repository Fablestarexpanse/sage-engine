# What a Modern MUD Engine Should Be: A First-Principles Platform Vision for 2026

## TL;DR
- A modern "MUD engine" should stop being a *game codebase you edit* and become a **world operating system**: a small, genre-agnostic simulation core (entities + components + rules + events + persistence) wrapped in tiered creation tools — natural-language and visual for laypeople, scripting and full APIs for developers — with a composable module marketplace and a rich browser client. The proven model is Foundry VTT and Roblox (a tiny system-agnostic core + a module/creator ecosystem), not DikuMUD (a hard-coded game).
- The single biggest failure of traditional MUDs is **tight coupling of world content to engine code**: builders must be programmers, worlds cannot be shared as portable modules, and communities die when their one maintainer leaves. The fix is a data-first world model, an event-sourced persistent simulation, and sandboxed, versioned, installable modules.
- **AI belongs as an optional creation and simulation *layer*, never as the runtime's foundation.** Determinism (rules, economy, combat, permissions, state) must be reproducible and vendor-independent; LLMs are best for authoring assistance, dynamic dialogue/narration, and automated playtesting — all behind graceful-degradation fallbacks because of hallucination, latency, cost, and vendor lock-in.

## Key Findings

**1. The old MUD family already discovered the core architectural fork — and the winner for a *platform* is clear.** Richard Bartle, co-author of the first MUD (Essex, 1978–80), and Raph Koster both describe three lineages: TinyMUD/MUSH/MOO (programmable, "live"-editable, social), LPMud (a driver/mudlib/LPC split), and DikuMUD (a hard-coded, out-of-the-box combat game). Koster notes the softcode platforms (MUSH, MOO, LPMud) were scriptable out of the box, had online creation support rather than flat text files, and — most importantly — had their core rulesets written *in the platform*. Diku was easiest to *run* but hardest to *change* — you edit C and recompile. The lesson: the platforms that empowered creators separated a stable core from content authored *inside* the system.

**2. Modern MUD frameworks converged on "unopinionated core + content bundles," but stop short of being creator platforms.** Evennia (Python/Django/Twisted, BSD) does not impose a style, genre or mechanic and abstracts away database and networking, but coding is done in normal Python modules — you still must be a programmer, and content lives in code. Ranvier (Node.js, MIT) built a bundle system where nearly every aspect of the game can be modified without changing the core and content is described in YAML — but by the maintainers' own admission it is a plain telnet MUD with no web client, and there are no popular released games on it. These are excellent *developer* frameworks and poor *layperson* platforms.

**3. The creator-economy playbook is proven at massive scale — and its concentration problem is the key warning.** Roblox's Developer Exchange fees reached $1,503.1 million in FY2025 (up 63% from $922.8 million in 2024), with over 23,500 creators receiving fiat payouts in 2025 and cumulative payouts exceeding $4 billion. But the economics are a power law: the top-1,000 creators averaged $1.3 million in 2025, while roughly 85% of developers earn under $100/month and the DevEx cash-out floor is 100,000 earned Robux (~$350). Foundry VTT proves a different, healthier model: a one-time-purchase, self-hosted, system-agnostic Node.js core with 475 approved game systems (+30% year-over-year) and thousands of modules, where only the host buys a license. Both validate "small core + module ecosystem"; Foundry validates a non-extractive, self-hostable governance model.

**4. Entity-Component-System is the right world model, and it directly answers "what is the minimum foundation."** ECS emphasises composition over inheritance, building entities from reusable components, with systems that act on any entity holding the required components — new systems can be introduced at any stage and automatically match existing entities. This is what lets *one* engine represent a sword, a spaceship, a corporation, and a weather front without a hard-coded schema. The minimum universal foundation is therefore: **entities (IDs), components (typed data), systems/rules (behavior), an event bus, a spatial/containment graph, identity/permissions, and a persistence log.** Everything else — combat, magic, classes, levels — is an *optional module*, not core.

**5. Event sourcing is the natural fit for persistent, "living-while-you're-offline" worlds.** Event sourcing persists state as a sequence of state-changing events, giving a reliable audit log and the ability to reconstruct past states and run temporal queries. It is already used in virtual worlds and multiplayer games to record player movements and state changes, with snapshots to avoid replaying the entire log. This provides world history, rewind/debugging, and clean migrations — exactly what MUDs need for persistent economies and politics.

**6. AI is genuinely useful but structurally unreliable as a foundation.** The Stanford + Google Research "Generative Agents" work (Park et al., UIST '23) populated a Sims-like sandbox with 25 LLM NPCs and found they maintained character coherence and demonstrated believable proxies of humanlike behaviour in remembering, planning, reacting, and reflecting — with emergent social behavior (an unprompted party) via a memory-stream + retrieval + reflection architecture that outperformed ablated architectures. But LLMs have inherent failure modes: hallucination, self-contradiction from lack of global memory consistency, non-determinism across seeds, plus cost and latency. AI Dungeon is the cautionary tale: unpredictable and often nonsensical output, repetition loops, and a content-safety catastrophe. Conclusion: use AI for authoring, dialogue flavor, and testing; never let it own canonical state, rules, or moderation-critical decisions.

**7. Extensibility must be sandboxed and versioned, and fragmentation is the top ecosystem risk.** WebAssembly is the strongest sandbox for untrusted community code: a portable bytecode that runs inside a sandbox, where a module cannot interact with the host except through host-supplied imports, with fuel metering to stop infinite loops. Minecraft's modding history is the warning: the Forge/Fabric split created lasting fragmentation requiring bridges like Architectury, and some mods cannot coexist. Foundry's manifest-based dependency/compatibility system is the model to copy.

**8. The modern client is a solved problem in principle: structured data over a text stream.** GMCP (Generic MUD Communication Protocol) sends out-of-band JSON to clients so a server can transmit room numbers, exits, vitals, inventory and quest changes invisibly to the player, letting clients render bars, maps, and panels. GMCP's lineage runs ATCP (2008) → MSDP (2009) → ATCP2/GMCP (2010). Mudlet (open-source, Lua-scriptable, with a built-in mapper) already demonstrates the target UX. A 2026 engine should make this the default, not a bolt-on.

## Details

### Historical Lessons

- **MUD1 (Trubshaw & Bartle, Essex, 1978–1980)** established persistence, social presence, emergent player-created goals, and role-play as the medium's durable strengths — not graphics.
- **AberMUD (1987)** spread because it was released with a license allowing free non-commercial use and ported to Unix — *distribution and licensing*, not features, drove adoption.
- **TinyMUD (1988)** was expected to last weeks, lasted ~9 months, and seeded all the social MUDs and MOOs — proving that *social* worlds with *in-world building* have staying power.
- **LPMud (1989)** introduced the separation of infrastructure into a driver and a mudlib written in LPC — the direct ancestor of every modern "core engine vs. game logic" split.
- **DikuMUD (1990–91)** went the opposite way: a well-organised hard-coded game that ran out of the box. It won on ease of *operation* and seeded the entire combat lineage through to modern MMOs. But its world is welded to C code — the archetype of the coupling problem.
- **LambdaMOO (1990)** let regular users program in a language designed to be easy for non-programmers, building live through in-world commands. Its lessons cut both ways: strong social focus, but its governance history ("A Rape in Cyberspace," the wizard/ARB crises) is the founding case study in why **moderation and governance must be designed in**. And even MOO's friendly language meant complex systems still required significant programming ability.

Cross-cutting patterns: coupling kills sustainability; genres bifurcated by architecture (hard-coded combat vs. soft social); distribution and licensing decide reach more than raw capability.

### Problems With Existing Models

1. Creation requires programming (Evennia: Python; Ranvier: JS/YAML; Diku: C; MOO: real programming for anything non-trivial).
2. World content is coupled to engine internals; worlds can't be cleanly exported, forked, or shared.
3. Builders must understand infrastructure — databases, networking, server admin, permissions, combat math.
4. Testing is manual and lonely; no tooling finds broken quests, unreachable rooms, or economy exploits.
5. Publishing/discovery is fragmented (telnet lists); no unified store with ratings, versioning, one-click play.
6. The interface looks like 1994; great clients require player-side setup.
7. The community can only share whole games, not parts.

**The deeper barrier — the no-code "complexity ceiling."** No-code platforms are closed systems where a workflow the platform did not anticipate hits a wall; practitioner studies rank "less powerful than programming" and "complex issues still need coding" among top challenges, with vendor lock-in close behind. Escape hatches fail as *automated one-way conversions* (Webflow export drops dynamic features; Unreal removed Blueprint nativization because generated code was slower and harder to debug) but succeed as *complementary coexistence* (C++ base class / Blueprint subclass). Block-to-text programming skills do not transfer automatically. The evidence validates "the easy path must not block the powerful path" — but *only* if implemented as coexistence, not conversion.

### Modern Opportunity

WebSockets (WebTransport later) make a rich browser client the default; GMCP/MSDP decouple data from presentation; WASM sandboxing enables safe, language-agnostic plugins; event sourcing plus cheap persistent databases make deep persistence practical; LLMs + vector DBs + knowledge graphs enable authoring assistance and bounded dynamic content; generative media adds optional richness; creator-economy infrastructure is well understood.

### Platform Philosophy

1. The engine is a world OS, not a game.
2. Data-first, code-optional.
3. Deterministic core, probabilistic edges.
4. Layered access with no dead-ends (coexistence, not conversion).
5. Everything is a module; core is deliberately tiny.
6. Composability over monoliths.
7. Self-hostable and non-extractive by default.
8. Safety and governance are architecture, not policy afterthoughts.

### Core Architecture

**The minimum universal foundation:** entities; components; systems/rules; event bus/log (event-sourced with snapshots); containment/space graph (rooms are one special case); identity & permissions; scheduler/world clock; persistence & migration.

**What must NOT be in the foundation:** combat, hit points, levels, classes, skills, magic, inventory *semantics*, quests, crafting, economy, factions, weather, vehicles, specific genres, AND any hard dependency on an external AI provider.

**Four tiers:** Core Engine → Optional Frameworks → Community Modules → Custom Logic.

### Creator Architecture

A spectrum of authoring surfaces over the same underlying data: templates/foundations; forms & structured config; visual graph editors (knowing they get unwieldy at scale); natural-language + AI assistant that *generates deterministic, inspectable configuration*; reusable archetypes from the marketplace. Deterministic config and visual tools for anything that affects canonical state; natural language and AI for *authoring* and first drafts; scripting for complex logic; full APIs for services.

### Developer Architecture

Builder (embedded, hot-reloadable, sandboxed scripting) → Developer (full APIs, WASM modules, custom services) → Core dev (open-source internals). A creator's work at Layer 2 must be *the same artifacts* a developer edits at Layer 3–4, so graduating is additive, not a rewrite.

### Modular System

Versioned bundles with manifests declaring dependencies and explicit engine compatibility (Foundry's model); WASM sandboxing with capability-based imports and fuel metering; semver + resolver + compatibility gating; a small set of official standard interfaces so competing modules interoperate (the opposite of Forge/Fabric); migrations that transform event-sourced state.

### AI Architecture

**Belongs:** creation (rooms, NPCs, quests, dialogue, lore, first-draft rules — all as editable artifacts); development help (intent → deterministic config); testing (simulated players finding broken quests, exploits, dead ends); bounded gameplay (dynamic dialogue and narration grounded by deterministic state, with guardrails).

**Must not:** own canonical state, adjudicate rules, make sole moderation decisions, or be a hard runtime dependency. Every AI feature needs a deterministic fallback.

### World Model

Universe/World → Zones/Regions/Places (nodes in a containment/space graph) → Entities defined purely by components → Relationships as typed graph edges (ownership, membership, kinship, reputation) → Rules/Systems + Scripts → Events/History (append-only log) → Assets (content-addressable) → Permissions. Nothing about genre is encoded.

### Community Ecosystem

Searchable catalog with ratings and one-click play; Git-like versioning, forks, remixes with attribution; multi-creator worlds with role-based permissions; composable publishing of sub-artifacts; a non-extractive creator economy designed for the long tail; curation, standard interfaces, dependency gating, and moderation to prevent chaos. The nesting model works: Engine → World → Regions → Communities → Player-created content.

### Client/UI Model

Browser-first, MUD-at-heart; structured data drives the UI (GMCP-like channel); accessibility first-class; bring-your-own-client stays possible because the protocol is open and text-first.

### Security & Moderation

Sandbox all untrusted code; layered content moderation (automated scanning + human review + trusted reporting); governance by design (ownership, roles, dispute processes); identity and abuse controls; safety for minors and strong guardrails on AI-generated content.

### Hosting Model

Hybrid, open core: one-click hosted worlds for laypeople; self-hosted for control; private/LAN and institutional deployments; open-source engine core with proprietary layers limited to hosted convenience services.

### Technical Stack Options

- **TypeScript/Node:** huge ecosystem, one language client-to-server; weaker CPU-bound performance.
- **Rust:** top performance, first-class WASM host, memory safety; steeper contributor curve.
- **Elixir/BEAM:** outstanding concurrency and fault isolation, hot reload; smaller talent pool.
- **Python:** fastest to prototype, great AI libraries; performance and concurrency limits.
- **Recommendation:** a performant core (Rust or BEAM) hosting a sandboxed scripting layer (JS/TS or Lua via WASM) with a TypeScript browser client. WebSockets now, WebTransport later, WebRTC for voice. Append-only event store + snapshots; Postgres for projections; object storage for assets; vector DB + knowledge graph for AI grounding. Partition by world/zone for scaling.

### Example Creator Journey

*"A cyberpunk city where corporations control everything, citizens own businesses, gangs control neighborhoods, players become detectives."* Start from a template → describe the concept to the assistant, which drafts districts, corporations, gangs and NPCs as editable data → shape geography visually → set rules via forms → author content with templates + AI drafts → test with AI player-agents → invite collaborators → private → beta → public → install community modules. No programming at any step; every artifact inspectable and later script-editable.

### Example Developer Journey

A stealth/detection subsystem: scaffold a module with a manifest → define components (`Perception`, `NoiseEmitter`, `Concealable`) and a system → implement against the engine API, compile to WASM, declare capabilities → expose creator-facing config → provide migrations and standard-interface conformance → test, version, publish.

### Example Community Journey

A creator publishes a tactical combat module conforming to the standard "damageable/combatant" interface → another creator installs it with one click; the resolver checks compatibility → it interoperates with existing inventory and NPC modules → v2 ships with migration notes; the installing world upgrades with state migrated automatically.

## Recommendations

**Stage 1 — Prove the core.** ECS, event-sourced persistence with snapshots, containment/space graph, identity/permissions, world clock, WebSocket client with structured-data channel, one deterministic scripting layer. Gate: a persistent world survives restarts with full history and a developer builds a custom system without touching internals.

**Stage 2 — Prove the creator path.** Templates, form/visual config, AI authoring assistant generating inspectable config, reusable archetypes. Gate: a non-programmer builds and publishes a playable world in under a week.

**Stage 3 — Prove the ecosystem.** WASM packaging, dependency/versioning/compatibility gating, standard interfaces, marketplace, forking/remixing, moderation + governance tools. Gate: a module authored by one creator installs cleanly into another's world.

**Stage 4 — Scale and economy.** Hosted worlds, horizontal scaling, non-extractive payouts, voice/generative-media layers, AI playtesting as a service.

**Avoid:** baking any genre system into core; AI as a hard runtime dependency; walled-garden-only hosting; automated one-way tier conversions; moderation/governance as post-launch policy.

## Caveats

Historical facts, LLM failure modes, ECS/event-sourcing properties, protocol lineages, and platform statistics are sourced; the tiered architecture, "world OS" framing, stack recommendations, and staging plan are architectural recommendations derived from that evidence. The prompt's assumptions were challenged: "AI does everything" is rejected; the room model is generalized to a graph; text-only is rejected in favor of hybrid; pure no-code is rejected because of the documented complexity ceiling. No existing system fully implements this; the closest partial proofs are Foundry VTT, Evennia/Ranvier, Roblox/Core, and Smallville — none combines a genre-agnostic ECS/event-sourced core, tiered no-dead-end authoring, a sandboxed composable marketplace, and a modern MUD-native client. The single greatest risk is feature creep in the core.
