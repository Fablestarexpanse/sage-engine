# Demo world with agents

The setting-neutral demo world plus ten scripted agents (ids 109-118). Every agent is zero-AI:
its `sage.mind` is a rule list, so the world plays with no model, no network and no randomness
beyond a fixed hash. Agents greet whoever says "good day", answer `tell`, greet others now and
then, look around, and wander.

Generated from `worlds/demo/seed.json`. The M3 S2 gate runs it for one hour of world time in
fast mode (`crates/sage-server/tests/agents.rs`).

```bash
cargo run -p sage-build -- plugins
cargo run --release -p sage-server -- run agents.db --seed worlds/demo-agents/seed.json --plugin target/plugins/sage.dialogue
```
