# 0017 — Component upcasters, memory importance and retrieval

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** "a component version mismatch is refused" in 0005 (now refused only without an upcaster)

## Context

M3 S3b, part 1. Owner rulings: importance comes from deterministic rules with optional per-kind weights in the mind, and relevance falls back to word overlap when there's no embedding endpoint. The weights need new `sage.mind` fields. Existing logs, including the committed 2a715f3 fixture, store minds at v1. Until now any component version change was refused, so a real component migration mechanism had to come first.

## Decision

**Component upcasters.** `ComponentRegistry::register_upcaster::<C>(from, step)` converts stored component data from version `from` to `from + 1`. A `ComponentSet` at an older version is upcast step by step before validation, in events and in snapshots, since restore applies snapshots as events. Stored data is never rewritten; a new snapshot stores the current version. Refused:
- an older version with a missing step
- a version newer than the registered one
- version 0
- an upcaster that fails (reported as bad component data)

**`sage.mind` v2** adds `importance: {kind: weight}` (each weight 0–10; keys must be occurrence kinds) and `reflect_threshold` (above 0; used in part 3). v1 → v2 leaves the data unchanged, since both fields default. The fixture log and `worlds/demo-agents` (still written at v1) load through it.

**Importance** (`retrieval::importance`, 0–10), unless the mind names a weight for the kind:
- 1: the agent's own command
- 2: its other own acts
- 7: its own reflection
- 8: anything aimed at it (it is a target)
- 6: speech that names it as a whole word
- 4: other speech
- 2: travel
- 3: anything else

**Retrieval** (`retrieval::select`). A prompt shows, oldest first:
- the 5 newest memories
- the 3 most important of the rest
- the 10 best of the rest by recency + importance/10 + relevance, where recency halves every 2,400 ticks (10 minutes at 4 Hz) and relevance is 0–1

Ties go to the newer memory. The importance slot wasn't in the Generative Agents design. It was added because a test showed an important message aimed at the agent crowded out by 45 lines of chatter, all similar to the recent conversation. Relevance alone can't separate those.

**Lexical relevance** (the no-endpoint fallback): cosine similarity of word sets, counting only words of 3+ letters and dropping a short English stopword list. The list covers lexicon verbs such as "says" and "tells", which appear in nearly every line. It's English-leaning on purpose; embeddings (part 2) are the multilingual path.

**Prompt assembly moves to the worker.** `PromptParts::gather` runs on the main thread: system message, contained candidate texts with importance, and a query made of the place, who's present and the last three lines. `PromptParts::assemble` runs on the worker thread with a relevance per candidate. Part 2 can then compute embeddings without ever blocking a tick.

## Consequences

- **Tested:**
  - Old component data is upcast through events and snapshots, and refused with no step, with a newer version, or with bad data.
  - The importance rules and weight overrides.
  - v2 mind validation.
  - A v1 mind still applies.
  - Recency decay, lexical relevance (including that a shared "says" is not relevance), and the selection rule.
  - A real prompt keeps an old, important tell while dropping old chatter.
- Importance is recomputed at think time from the current world (for example the agent's name), not stored. It's still deterministic for a given log and tick.
