# Phase 04: License report

**Milestone:** M2 — SAGE engine decoupling
**Status:** todo
**Depends on:** phase-01
**Estimated diff:** ~400 lines
**Tags:** language=python, kind=feature, size=m

## Goal

Brief locked decision 4 asks for an early dependency-license audit ahead of a possible paid
release, and the engine is now under FSL-1.1-ALv2. Phase 0 could only audit against a polluted
global interpreter (`docs/sage/PHASE0_AUDIT.md` §12). This phase adds a reproducible report over
the three dependency ecosystems, run in CI from a clean environment, with a policy that fails
the build on strong-copyleft or unidentified licenses in shipped dependencies.

## Architecture references

- `docs/sage/PHASE0_AUDIT.md` §12 — known findings (elkjs EPL-2.0, MPL-2.0 transitives).
- `NOTICE`, `LICENSE-FAQ.md` — the engine's own license.

## Current state

- `requirements.lock` pins 44 Python runtime packages (uv pip compile).
- `admin-ui`, `player-ui`, `worldforge` have `package-lock.json` v3; every package entry carries
  a `license` field and a `dev` flag.
- `worldforge/src-tauri/Cargo.lock`; `cargo metadata --format-version 1 --locked` resolves every
  crate with its `license` expression (downloads crate manifests).
- CI jobs: `python`, `worldforge`, `live`.

## Spec

1. **Classifier** — `scripts/license_report.py` (stdlib only): `classify(expression)` returns one
   of `permissive`, `weak`, `unknown`, `strong` for an SPDX-style expression. `OR` picks the
   most permissive branch, `AND` the most restrictive; parentheses and `/` (legacy npm
   "MIT/X11") are handled. Strong: `GPL*`, `AGPL*`, `SSPL*`. Weak: `LGPL*`, `MPL*`, `EPL*`,
   `CDDL*`. Permissive: MIT, MIT-0, BSD-*, 0BSD, Apache-2.0, ISC, Unlicense, Zlib, PSF-2.0,
   Python-2.0, CC0-1.0, CC-BY-4.0, BlueOak-1.0.0, Unicode-*, and common long-form names
   (e.g. "MIT License", "Apache Software License", "BSD License").
2. **Collectors**
   - Python: for each name in `requirements.lock`, read the installed distribution with
     `importlib.metadata`: `License-Expression`, else a short `License` field, else the
     `License ::` trove classifiers.
   - npm: each `package-lock.json` in the three apps; `dev: true` entries are dev-only.
   - Cargo: `cargo metadata` for `worldforge/src-tauri`, excluding workspace members. Skipped
     with a note if `cargo` is missing, unless `--require-cargo`.
3. **Policy** — shipped (non-dev) dependencies classified `strong` or `unknown` fail unless listed
   in `scripts/license_allowlist.toml` (`[[allow]]` with `ecosystem`, `name`, `reason`). `weak`
   entries are listed for review but never fail. Dev-only entries never fail.
4. **Output** — `--out <file>` writes Markdown: per-ecosystem counts by class, then every weak,
   unknown, strong and allowlisted entry with its app/source. Exit 1 on policy violations.
5. **CI** — a `licenses` job: checkout, Python 3.11, `pip install -r requirements.lock`, run
   `python scripts/license_report.py --require-cargo --out license-report.md`, upload the report
   with `actions/upload-artifact@v4` (also on failure).
6. **Tests** — `tests/test_license_report.py` (hermetic).

## Acceptance criteria

- [ ] Report runs in the clean venv from phase 01 with cargo, exits 0, and lists elkjs EPL-2.0
      as weak.
- [ ] A synthetic GPL-3.0 runtime package makes the policy fail; allowlisting it passes.
- [ ] CI `licenses` job green and uploads `license-report.md`.
- [ ] Gates and invariant ratchet pass.

## Test plan

- `test_classify_expressions` — MIT, `Apache-2.0 OR MIT`, `MIT AND GPL-3.0`, `(MIT OR GPL-2.0)`,
  `LGPL-2.1+`, `MIT/X11`, `Apache Software License`, nonsense → unknown.
- `test_python_metadata_prefers_expression_then_classifiers` — fake metadata objects.
- `test_npm_lock_collects_dev_flags` — temp lockfile.
- `test_policy_fails_strong_and_unknown_unless_allowlisted` — including dev-only exemption.

## Authorizations

- [x] May create `scripts/license_report.py`, `scripts/license_allowlist.toml`,
      `tests/test_license_report.py`; edit `.github/workflows/ci.yml` (new job).

## Out of scope

- Replacing any dependency. Findings are reported to the owner.
- `npm audit` security advisories.

## Update Log

<!-- entries appended below this line -->
