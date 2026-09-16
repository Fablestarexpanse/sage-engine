# Decision log

Owner rulings and measured facts, dated, newest last. Anything hard to reverse also gets an ADR.

## 2026-09-16

- **Fresh start.** v1 was renamed to `sage-engine-v1`, tagged `v1-final` (`4362edf`), made private and archived. It had 0 stars and 0 forks. A bundle backup was verified at `F:\Cursor Projects\SAGE-v1-backup\sage-engine-v1.bundle` (33 MB, all refs). `sage-engine` was re-created empty. See ADR 0001.
- **Stack:** Rust. The owner declined the two-week TypeScript spike. See ADR 0002.
- **License:** Apache-2.0 + CLA. The CLA stays a placeholder until a lawyer reviews it. See ADR 0003.
- **Build order:** bottom-up with milestone gates, as in blueprint §I. See ADR 0004.
- **Denylist:** seeded from v1 `scripts/sage_denylist.toml` plus the reference world's name and stat keys. The negative test works: a comment containing `Rivermoot` or `conduit_power` in a crate fails the check, while `resolve_path` passes.
