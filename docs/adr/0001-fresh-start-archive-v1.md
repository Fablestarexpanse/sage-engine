# 0001 — Fresh start: archive v1, clean-history repository

- **Status:** accepted
- **Date:** 2026-09-16
- **Supersedes:** none

## Context

SAGE v1 was pulled out of an existing game. Its decision log shows the damage: rename shims, an invariant ratchet fighting hardcoded setting terms, and two sources of truth (Redis flushed to Postgres) that silently reverted edits. There was no real entity/component model, and three clients plus an MCP surface were built on an unstable world model. v1's public history also contained a proprietary world, and it was licensed FSL-1.1-ALv2, which clashed with the promise that others can sell what they build.

## Decision

- The v1 repository was renamed to `Fablestarexpanse/sage-engine-v1` and tagged `v1-final` at `4362edf`. It was then made private and archived. It had 0 stars and 0 forks, so nothing public was lost.
- A full `git bundle` backup of every v1 branch and tag is stored outside this repository (`F:\Cursor Projects\SAGE-v1-backup\sage-engine-v1.bundle`, verified).
- `Fablestarexpanse/sage-engine` was re-created empty, and v2 starts here with no v1 history.
- No v1 code is carried over. Its ideas are carried over as principles in the Founding Blueprint (`docs/research/03-sage-fragment-foundry-founding-blueprint.md`). The one thing reused directly is v1's setting-term denylist, which seeds `scripts/denylist.txt`.

## Consequences

- Proprietary world content is not in this repository's history.
- v1 is still available for reference through the private archive or the bundle, but nothing in v2 may import it.
- Links to the old repository URL now resolve to this new repository, not to v1.
