# First-party plugins

Each directory is a code fragment named by its id, holding a `fragment.yaml` and the Rust crate
that builds its `plugin.wasm`. The crate for `creator.slug` is named `creator-slug`. First-party
plugins get no native escape hatch: same sandbox, same manifest rules, same `sage check` as
community plugins.

```bash
cargo run -p sage-build -- plugins
target/debug/sage check target/plugins/sage.wander
```
