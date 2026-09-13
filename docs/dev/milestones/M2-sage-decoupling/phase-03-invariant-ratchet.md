# Phase 03: Invariant ratchet

**Milestone:** M2 — SAGE engine decoupling
**Status:** todo
**Depends on:** phase-01
**Estimated diff:** ~450 lines
**Tags:** language=python, kind=feature, size=m

## Goal

Put brief invariants 2, 3 and 4 (`docs/sage/BRIEF.md` §3) into CI as a **ratchet**
(`docs/sage/PHASE1_CONTRACTS.md` Part E, D.G item 2). A scanner counts, per engine file, the
world-specific terms and the hardcoded player-facing strings. CI fails if any file's count rises
above a committed baseline or a new file has any hits. Counts can only go down, and reach zero
as Phase 3 moves Fablestar out.

## Architecture references

- `docs/sage/PHASE1_CONTRACTS.md` Part E — the checks and their false-positive rules.
- `NOTICE` — which paths are engine during the transition.
- `docs/sage/PHASE0_AUDIT.md` §3, §6 — what the scanner should find today.

## Pre-flight

1. Read `docs/dev/STANDARDS.md`, the references above, and this whole doc.
2. The four gates pass on the current tree.

## Current state

- No invariant checks exist. `.github/workflows/ci.yml` has jobs `python`, `worldforge`, `live`.
- Engine paths during the transition (`NOTICE`): `src/`, `alembic/`, `admin-ui/`, `player-ui/`,
  `worldforge/`, `worldforge-mcp/`, `scripts/`, `tests/`.
- `scripts/` is not covered by the ruff gates and has pre-existing ruff findings.
- Player text leaves the server through `session.send(text)`, `SessionManager.broadcast(text)` and
  `session.end(reason, text)`; ~200 `.send(` calls in `src/fablestar`.
- No `worlds/` directory exists yet.

## Spec

1. **Denylist data** — create `scripts/sage_denylist.toml` with three lists:
   - `insensitive` (case-insensitive): the brief's seed list minus the case-sensitive words,
     plus audit findings: `fablestar`, `conduit`, `glyph`, `glyphstream`, `resonance`, `digi`,
     `fortitude`, `acuity`, `tidegate`, `aipub`, `test_isle`, `starter_zone`, `echo_credits`,
     `pixels`.
   - `sensitive` (exact case, because they are ordinary English or code words in lowercase):
     `Resolve`, `Presence`, `Reflex`, `Pixel`.
   - `acronyms` (exact case, standalone): `FRT`, `RFX`, `ACU`, `RSV`, `PRS`.
2. **Scanner** — create `scripts/sage_invariants.py` (stdlib + `tomllib` only), with:
   - `iter_engine_files(root)`: files under the engine paths with extensions
     `.py .js .jsx .ts .tsx .html .css .json .toml .rs`, skipping directories `node_modules`,
     `dist`, `target`, `__pycache__`, `.desloppify`, `.pytest_cache`, and files
     `package-lock.json`, `Cargo.lock`, the scanner, its denylist, its baseline and its test.
     Paths are reported POSIX-style relative to the repo root.
   - `find_terms(text, denylist) -> Counter[str]`: a hit needs a word boundary that respects
     `snake_case` and `camelCase` — the character before a match may not be a letter or digit of
     the same run (an uppercase match may follow a lowercase letter: `mudConduit`), and the
     character after may not continue the word in lowercase (`Conduits` counts via an optional
     plural `s`, `Resolved` does not). `resolve_project_root` and `Promise.resolve` never match
     `Resolve`.
   - `world_terms(root)`: if `worlds/*/stats.yaml` or `worlds/*/currencies.yaml` exist, add
     each attribute and currency `key` to the insensitive list (invariant 4 for any world). Parse
     with a minimal line reader for `key:` entries so the script needs no YAML dependency.
   - `count_player_literals(py_source) -> int`: AST walk counting calls to an attribute named
     `send`, `broadcast` or `end` where the player-text argument (first positional for
     `send`/`broadcast`, second for `end`) is a string constant, an f-string, a `+`/`%`
     expression involving a string constant, or a `"...".format(...)` call.
   - `scan(root) -> {"denylist": {path: n}, "player_literals": {path: n}}`, omitting zero counts.
   - `compare(baseline, current) -> list[str]` of violations: a path whose count exceeds its
     baseline, or a path absent from the baseline with any count.
   - CLI: `python scripts/sage_invariants.py check` (exit 1 and print violations; also print
     totals and how many files improved, reminding to run `update`), `update` (write the
     baseline, sorted, with totals), `report` (per-term totals).
3. **Baseline** — run `update` to create `scripts/sage_invariants_baseline.json` and commit it.
4. **CI** — in the `python` job, add a step after Lint:
   `python -m ruff check scripts/sage_invariants.py` and
   `python scripts/sage_invariants.py check`.
5. **Docs** — in `CLAUDE.md` "Testing", one short paragraph: the invariant ratchet, the two
   commands, and "never raise the baseline to make CI pass; lower it with `update` when you
   remove hits".

## Acceptance criteria

- [ ] `python scripts/sage_invariants.py check` exits 0 on the committed tree.
- [ ] Adding the word `Conduit` to any engine `.py` file makes `check` exit 1 naming that file.
- [ ] `python -m pytest tests/test_sage_invariants.py` passes.
- [ ] The four gates pass; `ruff check scripts/sage_invariants.py` passes.

## Test plan

`tests/test_sage_invariants.py` (loads the script by path with `importlib.util`):
- `test_snake_and_camel_boundaries` — `digi_balance`, `CONDUIT_KEY`, `ConduitGlassStrip`,
  `stats.conduit` match; `conduction` does not.
- `test_sensitive_terms_ignore_code_words` — `resolve_project_root`, `Promise.resolve`,
  `presence_count` don't match; `"Resolve"` does; `Resolved` doesn't.
- `test_acronyms_standalone` — `FRT` matches in `"FRT/RFX"`; `FRTX` and `frt` don't.
- `test_player_literal_detection` — counts `session.send("x")`, `session.send(f"{a}")`,
  `session.send("a" + b)`, `session.end("r", "bye")`; ignores `session.send(msg)`,
  `ws.send(json.dumps(p))`.
- `test_compare_ratchet` — increase fails, decrease passes, new file with hits fails.
- `test_world_terms_from_packages` — a temp `worlds/demo/stats.yaml` with `key: might` adds
  `might`.

## End-to-end verification

1. `python scripts/sage_invariants.py check` on the tree — quote the totals line.
2. Append `# Conduit` to `src/fablestar/app.py`, run `check`, quote the violation and exit code,
   then revert.
3. `python scripts/sage_invariants.py report` — quote the top terms.

## Authorizations

- [x] May create `scripts/sage_invariants.py`, `scripts/sage_denylist.toml`,
      `scripts/sage_invariants_baseline.json`, `tests/test_sage_invariants.py`.
- [x] May edit `.github/workflows/ci.yml` (`python` job step) and `CLAUDE.md` "Testing".

## Out of scope

- Removing any hits (that is Phase 3).
- The import-boundary check (invariant 1) — lands with `engine/` and the plugin loader in 2c.
- JSX text-literal lint for the React clients (after 2b).
- Fixing pre-existing ruff findings in other `scripts/` files.

## Update Log

<!-- entries appended below this line -->
