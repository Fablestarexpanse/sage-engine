# Agent Life Roadmap — what agents need to live on Tidegate Isle

Owner question (2026-09-12): "figure out what our agents will need to live in
game and play their characters." This is the gap analysis between what the
agent stack does today and what a resident of the island needs, plus a build
order. Ground rule stays absolute: agents act only through the
CommandDispatcher — every capability below is a *player* capability that
agents then use.

## What already works (foundation)

| Need | Status |
|---|---|
| A body that survives | Reflexes: flee / fight / eat-when-hurt / rest-in-safe-rooms / wander routines |
| Feelings | Deterministic mood + needs (rest, company, purpose, safety), bonds, decay to persona baseline |
| A voice | Embedded LLM replies when addressed by a player (sanitized, cooldown, dedupe) |
| Wants | Intent goals every ~90s near players: wander_to / hunt / rest / talk / scavenge / idle |
| Memory | 40-event ring in the stats blob, fed to prompts, survives restarts |
| Mortality | Death → clinic respawn at half hp, deaths counter, memory of dying |
| Progression plumbing | Same conduit attributes + proficiency engine as players; XP progression chart |
| A place | Tidegate Isle: shops, clinic, AIpub with apartments, wilds with salvage and danger |
| Observability | Watch table, detail drawer (inventory/skills/POV), Stat board, persona editor |

## The gaps — what "living" still needs

### 1. Money (blocks nearly everything else)
Agents have no wallet. Players keep `digi_balance` on the DB character row;
agents have nothing. Without money there is no buying, selling, renting,
clinic bills, or reason to work.
**Build:** `digi` int in the agent stats blob (durable via agent_state flush);
show it in the watch table and Stat board.

### 2. An economy to participate in (the shops are set dressing)
There are no `buy` / `sell` / `trade` commands for anyone. The four market
shops and the AIpub bar have no stock, no prices, no way to spend.
**Build:** a `shop` block on room YAML (stock: template → price, buys:
tags/templates at a rate), `buy <item>` / `sell <item>` / `list` commands
through the dispatcher, `trades` counter (the Stat board grows the column
automatically). Aldo's pawn shop buys salvage — that turns Sela's scavenging
into income: search → carry → sell → digi. This is the core survival loop.

### 3. Hunger (a reason to spend)
Eating currently only happens when hurt. Nothing pushes an agent to buy food.
**Build:** `hunger` need in the feelings vector, rising over time; high hunger
nudges valence down and (Body rule) eat if carrying food, else (intent) buy
food or scavenge for it. Ration packs become groceries, the general store
becomes load-bearing.

### 4. A home (rent at the AIpub)
The AIpub apartments exist as rooms; nothing assigns them. "Rest anywhere
safe" means nobody needs a home.
**Build:** `rent` command — pay N digi, get an apartment assignment (Redis +
durable), sleeping in *your* room restores rest faster and boosts safety;
rent lapses without payment (a recurring money sink). `rent_paid` counter.

### 5. Work (purpose need is aimless)
The purpose need rises but nothing structured satisfies it. Meanwhile the
faction mission engine already generates jobs — for players only.
**Build:** let agents accept and complete generated missions through the same
commands players use; intent gains a `work` goal that compiles to
mission-progress scripts. Purpose drops on completion, digi rewards arrive,
`missions_completed` counts.

### 6. Society (agents ignore each other)
The voice gate only answers non-agent speakers, so the AIpub stays silent.
**Build:** agent-to-agent conversation with hard budgets (one exchange pair,
long per-pair cooldown, only when idle in a social room, bonds shift on it).
This is where bonds + the pub earn their keep. Budget matters: naive
agent-agent chat is an infinite LLM loop.

### 7. Time (no day to build a life around)
No world clock: shops never close, nobody sleeps at night.
**Build (small):** a coarse day cycle (morning/day/evening/night from server
time), exposed in prompts and Body context — routines pick per-phase targets
(Meri opens the store at morning, everyone drifts pub-ward at evening,
sleep at night). Cheap and gives the island a heartbeat.

### 8. Consequences (death is free)
Respawn costs nothing, so safety is only a feeling.
**Build:** clinic bill on respawn (digi deduction, debt if broke) — makes the
safety need economically real and gives Tessa's clinic a business.

### 9. Progression actually progressing (found while building the XP chart)
Nobody — player or agent — can gain a proficiency leaf in the field:
`try_field_gain` hits `depth_gate` because a tier-3 leaf needs its parent
branch at 15, and no in-game path raises parent branches at all. 68 drone
kills = 0 levels. The XP chart will stay flat until this is decided.
**Owner decision needed:** either (a) parents auto-raise as the sum/max of
their leaves, (b) waive the gate below some tier, or (c) ship the archive
spending flow that raises branches. (a) is the smallest change that makes
field play progress.

## Suggested build order

1. **E1 — the survival loop** (unblocks most): agent digi wallet → shop
   blocks + buy/sell/list → pawn shop buys salvage → clinic respawn bill.
   Verify: Sela scavenges the beach, sells at Aldo's, eats bought rations,
   pays a clinic bill after a drone gets her.
2. **E2 — a life**: hunger need → rent + own-bed sleep at the AIpub →
   day cycle phases in routines.
3. **E3 — a mind in a society**: missions for agents (work goal) →
   budgeted agent-to-agent talk in social rooms → bond-driven behavior.
4. **In parallel, owner call:** the depth-gate decision (9) so the XP
   chart moves.

Everything lands as player-usable systems first (buy/sell/rent/missions all
work for humans), with agents as their heaviest users — the test the owner
asked this sandbox to run.
