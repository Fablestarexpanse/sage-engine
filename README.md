# SAGE — Synthetic Agent Game Engine

Worlds are built, not scripted.

SAGE is an open-source, self-hosted engine for persistent text worlds. It has a small core that knows no genre: entities and components, an event log as the only source of truth, a space graph, identities and a world clock. Everything else ships as a **fragment**. Content fragments are data, such as agents, places, items and lorebooks, often packed as PNG cards. Code fragments are signed WASM components that must declare every engine interface they use. Synthetic agents are ordinary entities with a mind. They act through the same commands a player types.

Fragments are shared through [Fragment Foundry](https://fragmentfoundry.com), which never runs worlds.

## Status

M1 (world model) in progress. The event log, snapshots, space graph, world clock and run loop exist. See [docs/STATUS.md](docs/STATUS.md).

| Milestone | Scope |
|---|---|
| M1 | World model: entities, components, space graph, event log, snapshots, tick |
| M2 | Plugin seal: WIT API, Wasmtime host, manifest validation, `sage check` |
| M3 | Synthetic agents: Mind component, scripted then LLM drivers |
| M4 | Player client and Foundry MVP |
| M5 | Workshop editors and social layer |
| M6 | Marketplace |

A layer does not start until the previous milestone's gate tests pass ([ADR 0004](docs/adr/0004-build-order-and-milestone-gates.md)).

## Read first

- [Founding Blueprint](docs/research/03-sage-fragment-foundry-founding-blueprint.md)
- [Architecture decision records](docs/adr/)
- [Decision log](docs/DECISIONS.md)

## Build

```bash
cargo build --workspace
cargo test --workspace
scripts/check-denylist.sh
```

## Run the demo world

```bash
cargo run --release -p sage-server -- run demo.db --seed worlds/demo/seed.json --wander-every 20
cargo run --release -p sage-server -- inspect demo.db
```

`sage run` ticks at 4 Hz until Ctrl-C. There is no network client yet; that arrives at M4.

## Previous version

SAGE v1 (Python/FastAPI) is archived and private. This repository starts with a clean history ([ADR 0001](docs/adr/0001-fresh-start-archive-v1.md)).

## License

Apache-2.0. See [LICENSE](LICENSE). You can build worlds and fragments on SAGE and sell them under any terms you choose. Contributions require the [CLA](CLA.md).
