# SAGE — Synthetic Agent Game Engine

Worlds are built, not scripted.

SAGE is an open-source, self-hosted engine for persistent text worlds. It has a small core that knows no genre: entities and components, an event log as the only source of truth, a space graph, identities and a world clock. Everything else ships as a **fragment**. Content fragments are data, such as agents, places, items and lorebooks, often packed as PNG cards. Code fragments are signed WASM components that must declare every engine interface they use. Synthetic agents are ordinary entities with a mind. They act through the same commands a player types.

Fragments are shared through [Fragment Foundry](https://fragmentfoundry.com), which never runs worlds.

## Status

M1 (world model), M2 (plugin seal) and M3 (synthetic agents) are done. M4, the player client and Fragment Foundry MVP, is in progress: players can sign in and play from a browser. The event log, space graph, world clock and run loop exist, along with sandboxed WebAssembly plugins, fragment manifests, `sage check`, commands, and scripted and LLM-driven agents whose memory is rebuilt from the log. See [docs/STATUS.md](docs/STATUS.md).

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
cargo run -p sage-build -- plugins
cargo run --release -p sage-server -- check target/plugins/sage.wander
cargo run --release -p sage-server -- run demo.db --seed worlds/demo/seed.json --plugin target/plugins/sage.wander
cargo run --release -p sage-server -- inspect demo.db
```

Agents run with no AI by default. To let `hybrid` and `llm` agents ask a model, point `sage run` at any OpenAI-compatible API, such as local Ollama:

```bash
cargo run --release -p sage-server -- run agents.db --seed worlds/demo-agents/seed.json --llm-url http://localhost:11434/v1 --llm-model llama3.2
```

If the endpoint needs a key, set `SAGE_LLM_API_KEY`.

`sage-build plugins` compiles the first-party plugins in `plugins/` to WebAssembly components. `sage run` loads a plugin only if `sage check` passes, grants it exactly the interfaces its manifest declares, and ticks at 4 Hz until Ctrl-C.

## Play in a browser

```bash
pnpm --dir client install
pnpm --dir client build
cargo run --release -p sage-server -- run agents.db --seed worlds/demo-agents/seed.json --listen 127.0.0.1:4700
```

Open `http://127.0.0.1:4700/`, create a character, and type commands (`look`, `say hello`, `go onward`). The client is built into the binary; without Node the engine still builds, and any WebSocket client can play at `/ws` ([ADR 0021](docs/adr/0021-player-protocol-and-accounts.md)). Bind to `127.0.0.1` unless a TLS reverse proxy sits in front.

## Previous version

SAGE v1 (Python/FastAPI) is archived and private. This repository starts with a clean history ([ADR 0001](docs/adr/0001-fresh-start-archive-v1.md)).

## License

Apache-2.0. See [LICENSE](LICENSE). You can build worlds and fragments on SAGE and sell them under any terms you choose. Contributions require the [CLA](CLA.md).
