# 0018 — Embedding relevance and its rebuildable cache

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

M3 S3b, part 2. Owner ruling: relevance uses embeddings from an OpenAI-compatible endpoint, cached where the cache can be rebuilt and is never canonical, with word overlap as the fallback. Word overlap can't match meaning: a question about the "ferry" misses a memory about the "boat".

## Decision

**`Embedder`** turns texts into vectors. `HttpEmbedder` posts `{model, input: [texts]}` to `{url}/embeddings` and reads `data[i].embedding`. It honours the `index` field, and refuses count mismatches, non-numbers and missing vectors.

**`EmbeddingCache`** is a SQLite table `(model, text, vector)` keyed by model and *exact text*. Keying by text rather than a hash means a collision can't hand back the wrong vector. `sage run` keeps it in `<world>.embeddings.db`, beside the world and never inside it. Deleting the file costs only recomputation (tested: after deletion the scores come back identical).

**`Relevance`** is either `Lexical` or `Embedded`. It runs on the worker thread while a prompt is assembled (the move from ADR 0017), so embedding calls never block a tick.
- **What gets embedded:** the query and every candidate. Only texts missing from the cache are sent, in one batch.
- **Scoring:** cosine similarity, with negative values clamped to 0.
- **Failure:** relevance falls back to word overlap for that prompt. The embedder rests for 60 s, and one warning is reported per failure, not per request.

**CLI:**
- **Flags:** `--embed-url <url> --embed-model <name>`, which must be given together and need `--llm-url`, since embeddings only choose what a model sees.
- **Key:** `SAGE_EMBED_API_KEY`, falling back to `SAGE_LLM_API_KEY`.
- **Warnings:** go to stderr through the new `Collected::warnings`.

## Consequences

- **Tested with an in-process embedder that places texts by topic:**
  - Embeddings pick "The boat crosses at dawn" for a ferry question where word overlap doesn't.
  - The first prompt embeds query and candidates in one batch, and a repeat needs no calls.
  - A new memory is the only text sent.
  - A reopened cache file needs no calls, and a deleted one is rebuilt with identical scores.
  - A failing endpoint yields word overlap, one warning, and no retry while resting.
- **`HttpEmbedder` against a stub:** the request line, model and inputs are correct, and out-of-order answers are placed by `index`.
- **The real `sage` binary** with `--embed-*` against a stub embedded memories and wrote `dock.db.embeddings.db` rows for the model.
- **Not yet run against a real embedding model** such as Ollama's `nomic-embed-text`.
- **Cache growth:** the cache grows with every distinct memory text and is never pruned. Pruning, or keeping only the last N days, is deferred until a real world shows the size matters.
