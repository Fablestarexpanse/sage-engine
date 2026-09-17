# Demo world

A small world with no setting: places joined by ways, and numbered markers to move around. It is
the engine's test bed, and the proof that a world boots and plays with every AI driver turned off.
`worlds/demo-agents/` is the same world with ten agents added.

```bash
cargo run --release -p sage-server -- run demo.db --seed worlds/demo/seed.json
```

Its name is still an open question (see docs/STATUS.md).
