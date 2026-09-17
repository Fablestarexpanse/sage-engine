# 0019 — Reflection

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M3 S3b, part 3. Owner ruling: when the summed importance of new memories passes a threshold, the model writes 1–3 reflections. They're stored as `sage.mind.reflected` occurrences that only the agent perceives, and they then enter memory and retrieval. Plans are deferred.

## Decision

**When.** Only `hybrid` and `llm` minds reflect, and only with a model configured. At each due think, if the model is available for the agent:
- **The sum:** everything perceived *since its last own reflection*, scored by the importance rules (earlier reflections excluded).
- **The threshold:** `reflect_threshold`, defaulting to 50.
- **Priority:** if the sum reaches the threshold, a reflection request goes out instead of acting that think.

The trigger is computed from memory, which is rebuilt from the log, so a restarted world never reflects twice on the same memories (tested).

**How.** A separate request purpose with its own prompt:
- **System:** write 1–3 insights, persona and goals, and the `<perceived>` rule.
- **User:** the memories since the last reflection, selected as usual and closed with "What does X conclude?".

`Transport::complete` now takes the `response_format`, so action and reflection requests each demand their own schema. `reflection::check_reflections` accepts exactly `{"reflections": [...]}` with 1–3 non-empty strings of at most 200 characters and no control characters.

**Stored as ordinary history.** Accepted reflections come back in `Collected::reflections` and are handed to `reflection::Reflections`, a native scheduler system. On the next step it commits each one as `sage.mind.reflected` (actor: the agent, no places, no targets), inside that tick's transaction. The journal fills the audience in as `[agent]`. Plugins still can't emit `sage.*` kinds; this is engine code. The lexicon line is `sage.mind.reflected.self` = "You think: {text}". A reflection's importance is 7, so it tends to stay in later prompts.

**Failures.** A failed reflection, refused or unreachable, backs that agent off reflection for 100 ticks. Otherwise an over-threshold agent would ask again on every think. The backoff is in memory only; at worst a restart retries one reflection early.

**`sage run`** adds the `Reflections` system, merges the agents' lexicon, and reports `reflections=N`.

## Consequences

- **Tested against a stub model:**
  - Four lines naming the agent (importance 6 each, threshold 20) trigger exactly one reflection request carrying those memories.
  - Two reflections are logged with audience `[3]` only, and the next action prompt contains "You think: …".
  - A restart doesn't reflect again.
  - A four-item reply is refused and not retried within the backoff.
  - Scripted minds never call the model.
- **Mutation:** making the importance sum ignore the last reflection fails both the restart test and the first test, because the agent reflects on the same memories again.
- **Retrieval:** Smallville's reflection also asks questions first and retrieves per question. Here the whole since-last-reflection window goes to one call. It's simpler and cheaper; revisit if reflections come out shallow with real models.
- **Real models:** not run against one yet.
