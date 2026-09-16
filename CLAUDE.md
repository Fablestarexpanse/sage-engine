# SAGE v2 — agent rules

Read `docs/STATUS.md` first. Its `NEXT:` line tells you where work stopped. Then read the ADRs in `docs/adr/`. The design source is `docs/research/03-sage-fragment-foundry-founding-blueprint.md`.

## Hard rules

1. **Gates before layers.** Don't write code for a later milestone (ADR 0004) until the current gate's tests pass. No client, editor, MCP server or Foundry work before M4.
2. **One source of truth.** The event log (SQLite) is canonical. In-memory ECS state is a projection. Never add Redis or any second store.
3. **Everything persisted is versioned.** Events carry `schema_version`. Components, manifests and WIT packages carry versions. Unversioned persisted data is a bug.
4. **No setting terms in engine code.** `scripts/check-denylist.sh` must pass. Genre mechanics (combat, levels, economy and similar) are fragments, never core.
5. **No proprietary world content in this repo.** Not in code, fixtures, tests or docs.
6. **Deterministic code decides; LLMs only describe.** Every AI path has a fallback that works with no AI. Agents act only through the player command interface.
7. **Space is a graph.** Don't call the engine "room-based".
8. **Dependencies enter with the milestone that needs them.**
9. **Record decisions when they happen.** Owner rulings go in `docs/DECISIONS.md`. Hard-to-reverse choices get an ADR. Update the `NEXT:` line in `docs/STATUS.md` before stopping.
10. **Stop after each agreed step** and show a real run. The commit message says what now refuses that didn't before.

## Checks (all must pass before commit)

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
scripts/check-denylist.sh
```
