# Contributing

SAGE is solo-maintained at this stage. Outside pull requests wait until the [CLA](CLA.md) is finalized.

## Rules the project holds itself to

- **Milestone gates.** Work for a layer does not merge until the gate tests of the layer below pass. See [ADR 0004](docs/adr/0004-build-order-and-milestone-gates.md).
- **One decision, one ADR.** A choice that is hard to reverse gets a file in `docs/adr/` built from `0000-template.md`. When a decision changes, write a new ADR that supersedes the old one. Do not edit the old one.
- **No setting terms in engine code.** `scripts/check-denylist.sh` runs in CI. If a real engine concept collides with a listed term, record the call in an ADR.
- **No proprietary worlds here.** Worlds that are not open source live in their own repositories.
- **One store.** The event log is the only source of truth. Don't add a cache that can drift from it.

## Checks

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
scripts/check-denylist.sh
```
