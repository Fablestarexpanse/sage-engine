# Phase 01: Parser + Registry Tests

> **Historical record (marked 2026-09-13).** Kept as written for the reasoning trail; do not
> treat as current instructions. Superseded by: `docs/dev/milestones/M2-sage-decoupling/` (it remains a good example of the phase-doc format).

**Milestone:** M1 — Code Quality Foundation
**Status:** done
**Depends on:** none
**Estimated diff:** ~130 lines
**Tags:** language=python, kind=test, size=s

## Goal

Add `tests/test_parser.py` covering the tokenizer, `CommandRegistry`, and
`CommandDispatcher`. These modules are pure logic (no Redis, no Postgres, no
network), making them ideal first targets. Brings the test count from 13 to
~30 and gives the command pipeline its first regression coverage.

## Architecture references

Read before starting:

- `docs/architecture.md#layer-2--game-engine` — command pipeline diagram
  (tokenize → registry.get → handler)

## Pre-flight

1. Read `docs/dev/STANDARDS.md` top to bottom.
2. Read the architecture reference above.
3. Read this entire phase doc before touching any code.
4. Confirm all four gates pass on the current tree before adding anything:
   ```
   python -m ruff format --check src tests
   python -m compileall -q src tests
   python -m ruff check src tests
   python -m pytest
   ```
   All must exit 0. If any fail, stop and file a blocker.

## Current state

Three source files this phase tests:

**`src/fablestar/parser/tokenizer.py` (lines 1–19)**
```python
def tokenize(input_string: str) -> list[str]:
    if not input_string:
        return []
    try:
        return shlex.split(input_string.lower())
    except ValueError:
        # Fallback for malformed quotes
        return input_string.lower().split()
```
Pure function. No dependencies on the server.

**`src/fablestar/commands/registry.py` (lines 11–80)**
```python
class Command:
    def __init__(self, name, handler, aliases=None): ...

class CommandRegistry:
    def register(self, name, handler, aliases=None): ...
    def get(self, name) -> Command | None: ...   # checks primary then aliases
    def reload_module(self, module_name): ...

registry = CommandRegistry()   # module-level singleton

def command(name, aliases=None):   # decorator
    def decorator(func):
        registry.register(name, func, aliases)
        return func
    return decorator
```
Registry is pure dict operations. The module-level `registry` singleton is
**shared state** — tests that use it must clean up after themselves or use a
fresh `CommandRegistry()` instance (preferred).

**`src/fablestar/parser/dispatcher.py` (lines 1–40)**
```python
class CommandDispatcher:
    async def dispatch(self, session: Session, raw_input: str):
        if not raw_input.strip(): return
        tokens = tokenize(raw_input)
        verb = tokens[0]; args = tokens[1:]
        command = registry.get(verb)   # reads the module-level singleton
        if command:
            await command.handler(session, args)
        else:
            await session.send(f"Unknown command: '{verb}'. ...")
```
`dispatch` is `async`. Calls `registry.get()` on the **module-level singleton**
(not a locally-injected registry). Tests must register commands into the
singleton and clean up afterward.

**`tests/test_proficiencies.py`** — the existing test file (pattern to follow):
```python
import unittest
from pathlib import Path

class TestBuiltinCatalog(unittest.TestCase):
    def test_leaf_count(self) -> None:
        rows = all_builtin_leaf_rows()
        self.assertEqual(len(rows), EXPECTED_LEAF_COUNT)
```
Use `unittest.TestCase` with descriptive present-tense method names.
Async test methods need `asyncio` — see the Async testing note below.

## Async testing

`CommandDispatcher.dispatch` is `async`. The pattern for async test methods
in stdlib `unittest` is:

```python
import asyncio
import unittest

class TestDispatcher(unittest.TestCase):
    def test_dispatches_known_command(self):
        asyncio.run(self._async_test())

    async def _async_test(self):
        # ... await dispatcher.dispatch(...)
        self.assertEqual(...)
```

`asyncio.run()` is the correct stdlib approach (Python 3.11). Do **not** add
`pytest-asyncio` or any new dependency — it is not authorized.

## Stub Session (for dispatcher tests)

`CommandDispatcher.dispatch` calls `session.send(message)` for unknown
commands and error paths. You need a stub `Session` that captures sent
messages without touching a real WebSocket. Write a minimal stub:

```python
class _StubSession:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)
```

Do **not** import the real `Session` class or `Protocol` — they pull in
network dependencies. The stub is a local-to-the-test-file duck type; it
only needs the `.send()` method that `dispatcher.dispatch()` calls.

## Module-level registry cleanup

`CommandDispatcher.dispatch` calls `registry.get(verb)` where `registry`
is the singleton at `fablestar.commands.registry.registry`. To test dispatch
without polluting other test runs, either:

1. Register a test command in `setUp` and remove it in `tearDown`:
   ```python
   from fablestar.commands.registry import registry

   class TestDispatcher(unittest.TestCase):
       def setUp(self):
           async def _handler(session, args): ...
           registry.register("testcmd", _handler)

       def tearDown(self):
           registry._commands.pop("testcmd", None)
   ```

2. Or pass a fresh `CommandRegistry()` to a locally-instantiated dispatcher
   (but note: the current `CommandDispatcher` does not accept an injected
   registry — it reads the singleton directly). Use approach 1.

## Spec

1. **Create `tests/test_parser.py`** — new file; add the three test classes
   below. Follow the `unittest.TestCase` pattern from `tests/test_proficiencies.py`.

### Task 1 — `TestTokenize`

Test the `tokenize()` function from `fablestar.parser.tokenizer`. Cases to
cover:

- `tokenize("")` returns `[]`
- `tokenize("  ")` (whitespace only) returns `[]`
- `tokenize("go north")` returns `["go", "north"]`
- `tokenize("GO NORTH")` returns `["go", "north"]` (lowercased)
- `tokenize('say "hello world"')` returns `["say", "hello world"]`
  (quoted string preserved as single token)
- `tokenize("say hello world")` returns `["say", "hello", "world"]`
  (no quotes = three tokens)
- `tokenize("cmd 'it\\'s broken")` returns tokens via the fallback
  `.split()` path (malformed quote triggers `ValueError`)

### Task 2 — `TestCommandRegistry`

Test `CommandRegistry` using a fresh instance (not the singleton):

```python
from fablestar.commands.registry import CommandRegistry

class TestCommandRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = CommandRegistry()
        async def _noop(session, args): pass
        self.handler = _noop
```

Cases:

- `reg.get("missing")` returns `None`
- After `reg.register("look", handler)`, `reg.get("look")` returns the
  `Command` with `.name == "look"` and `.handler is handler`
- After `reg.register("go", handler, aliases=["move", "walk"])`:
  - `reg.get("go")` returns the command
  - `reg.get("move")` returns the same command
  - `reg.get("walk")` returns the same command
  - `reg.get("run")` returns `None` (not an alias)
- `reg.register("look", handler)` with no aliases → `command.aliases == []`

### Task 3 — `TestCommandDispatcher`

Test `CommandDispatcher.dispatch()` using the module-level singleton registry
and a `_StubSession`. All test methods call `asyncio.run(...)`.

Cases:

- Empty input (`""`) — `dispatch` returns early, `session.sent` is `[]`
- Whitespace-only input (`"   "`) — same: early return, nothing sent
- Unknown command (`"xyzzy"`) — `session.sent` contains a string including
  `"xyzzy"` (the "Unknown command" message)
- Known command registered into the singleton — handler is called with
  the correct `args`; verify via a captured side-effect:
  ```python
  captured = {}
  async def _capture(session, args):
      captured["args"] = args
  registry.register("ping", _capture)
  # dispatch "ping foo bar" → captured["args"] == ["foo", "bar"]
  ```

## Acceptance criteria

- [x] `python -m pytest tests/test_parser.py -v` passes with ≥ 13 new tests.
- [x] `python -m pytest` passes (all 13 original + new tests).
- [x] `python -m ruff check src tests` exits 0.
- [x] `python -m ruff format --check src tests` exits 0.
- [x] `python -m compileall -q src tests` exits 0.
- [x] No new imports outside the standard library and the project's own
      `fablestar` package (no new dependencies).

## Test plan

In `tests/test_parser.py`:

- `TestTokenize::test_empty_string_returns_empty_list`
- `TestTokenize::test_whitespace_only_returns_empty_list`
- `TestTokenize::test_splits_on_spaces`
- `TestTokenize::test_lowercases_tokens`
- `TestTokenize::test_quoted_string_is_single_token`
- `TestTokenize::test_unquoted_multi_word_is_three_tokens`
- `TestTokenize::test_malformed_quote_falls_back_to_split`
- `TestCommandRegistry::test_get_missing_returns_none`
- `TestCommandRegistry::test_register_and_get_by_name`
- `TestCommandRegistry::test_get_by_alias`
- `TestCommandRegistry::test_all_aliases_resolve`
- `TestCommandRegistry::test_non_alias_returns_none`
- `TestCommandRegistry::test_no_aliases_defaults_to_empty_list`
- `TestCommandDispatcher::test_empty_input_sends_nothing`
- `TestCommandDispatcher::test_whitespace_input_sends_nothing`
- `TestCommandDispatcher::test_unknown_command_sends_error`
- `TestCommandDispatcher::test_known_command_calls_handler_with_args`

## End-to-end verification

```bash
python -m pytest tests/test_parser.py -v 2>&1 | tail -25
python -m pytest 2>&1 | tail -5
```

Quote the actual output in the completion Update Log.

## Authorizations

None.

## Out of scope

- Tests for command *handlers* (`commands/combat.py`, `items.py`, etc.) — they
  require live Redis/Postgres; deferred.
- Tests for `registry.reload_module()` — requires filesystem and import
  machinery; deferred.
- `pytest-asyncio` or any other new dependency — not authorized.
- Any changes to `src/` files.

## Update Log

<!-- entries appended below this line -->

### Update — 2026-06-20 17:08 (escalation — dispatch 1)

**Chosen lever:** refined re-dispatch (environment fix, not spec change)
**Rationale:** First dispatch hard_failed on `IdenticalToolCallRepetition`
(`find_files` ×6), but the root cause was environmental, not a spec gap: every
`bash` call returned `failed to spawn shell: program not found`. The rexyMCP
executor's bash tool and gate-command runner both `Command::new("sh")`
(`executor/src/tools/bash.rs:108`, `executor/src/agent/command.rs:33`), and the
server process's PATH lacked `C:\Program Files\Git\bin` where `sh.exe` lives
(`where.exe sh` → not found; only `…\Git\cmd` was on PATH). No spec refinement
could fix this. Fix applied to the rexyMCP plugin config
(`C:\Users\Brian\rexyMCP\plugin\.mcp.json`): added an `env.PATH` that prepends
`C:\Program Files\Git\bin`. Verified in simulation: with that PATH, `sh`
resolves to `…\Git\bin\sh.exe` and `sh -c "python -m ruff --version"` succeeds.
Requires the rexymcp MCP server to be reconnected so the new env takes effect
before re-dispatch. Phase spec unchanged; status stays `todo` (first dispatch
produced no work).

### Update — 2026-06-20 17:15 (escalation — dispatch 2 → takeover)

**Chosen lever:** session takeover
**Rationale:** Second dispatch (after PATH fix attempt) hard_failed on
`EmptyCompletionStall` (3 consecutive empty completions). Bash was still
unavailable to the executor — the `.mcp.json` `${PATH}` interpolation did not
take effect (server was not reconnected, or `${PATH}` is not expanded on
Windows). The executor did successfully write `tests/test_parser.py` (161 lines,
17 tests) via `write_file` before stalling. This is a second occurrence of the
same infra failure class; per the escalate skill's table, session takeover is
the correct lever after one refined re-dispatch has already failed.
Architect ran all four gates directly.

### Update — 2026-06-20 17:15 (complete)

**Summary:** `tests/test_parser.py` created by the executor (dispatch 2) and
gates run by architect takeover. File required one `ruff format` pass (executor
wrote it without a working shell to format on the fly). All 17 new tests pass;
full suite is 30/30.

**Acceptance criteria:** all ticked above.

**Commands:**

```
python -m ruff format src tests
1 file reformatted, 65 files left unchanged

python -m compileall -q src tests
(no output — exit 0)

python -m ruff check src tests
All checks passed!

python -m pytest tests/test_parser.py -v | tail -25
tests/test_parser.py::TestTokenize::test_empty_string_returns_empty_list PASSED
tests/test_parser.py::TestTokenize::test_lowercases_tokens PASSED
tests/test_parser.py::TestTokenize::test_malformed_quote_falls_back_to_split PASSED
tests/test_parser.py::TestTokenize::test_quoted_string_is_single_token PASSED
tests/test_parser.py::TestTokenize::test_splits_on_spaces PASSED
tests/test_parser.py::TestTokenize::test_unquoted_multi_word_is_three_tokens PASSED
tests/test_parser.py::TestTokenize::test_whitespace_only_returns_empty_list PASSED
tests/test_parser.py::TestCommandRegistry::test_all_aliases_resolve PASSED
tests/test_parser.py::TestCommandRegistry::test_get_by_alias PASSED
tests/test_parser.py::TestCommandRegistry::test_get_missing_returns_none PASSED
tests/test_parser.py::TestCommandRegistry::test_no_aliases_defaults_to_empty_list PASSED
tests/test_parser.py::TestCommandRegistry::test_non_alias_returns_none PASSED
tests/test_parser.py::TestCommandRegistry::test_register_and_get_by_name PASSED
tests/test_parser.py::TestCommandDispatcher::test_empty_input_sends_nothing PASSED
tests/test_parser.py::TestCommandDispatcher::test_known_command_calls_handler_with_args PASSED
tests/test_parser.py::TestCommandDispatcher::test_unknown_command_sends_error PASSED
tests/test_parser.py::TestCommandDispatcher::test_whitespace_input_sends_nothing PASSED
17 passed in 0.02s

python -m pytest | tail -5
30 passed in 0.43s
```

**End-to-end verification:**

`python -m pytest tests/test_parser.py -v` → 17 passed in 0.02s  
`python -m pytest` → 30 passed in 0.43s (13 original + 17 new)

**Files changed:**
- `tests/test_parser.py` — new file; 17 tests across TestTokenize, TestCommandRegistry, TestCommandDispatcher

**New tests:**
- `TestTokenize::test_empty_string_returns_empty_list`
- `TestTokenize::test_whitespace_only_returns_empty_list`
- `TestTokenize::test_splits_on_spaces`
- `TestTokenize::test_lowercases_tokens`
- `TestTokenize::test_quoted_string_is_single_token`
- `TestTokenize::test_unquoted_multi_word_is_three_tokens`
- `TestTokenize::test_malformed_quote_falls_back_to_split`
- `TestCommandRegistry::test_get_missing_returns_none`
- `TestCommandRegistry::test_register_and_get_by_name`
- `TestCommandRegistry::test_get_by_alias`
- `TestCommandRegistry::test_all_aliases_resolve`
- `TestCommandRegistry::test_non_alias_returns_none`
- `TestCommandRegistry::test_no_aliases_defaults_to_empty_list`
- `TestCommandDispatcher::test_empty_input_sends_nothing`
- `TestCommandDispatcher::test_whitespace_input_sends_nothing`
- `TestCommandDispatcher::test_unknown_command_sends_error`
- `TestCommandDispatcher::test_known_command_calls_handler_with_args`

**Notes for review:** Executor wrote the file correctly but couldn't run gates
(bash unavailable on Windows host). Architect ran format + gates. One ruff
format pass was needed; no other changes to the executor's output.

### Review verdict — 2026-06-20

- **Verdict:** escalated
- **Bounces:** 2 (dispatch 1: IdenticalToolCallRepetition/bash-unavailable; dispatch 2: EmptyCompletionStall/bash-still-unavailable — both infra, no code defects)
- **Executor:** Claude Code (direct takeover after 2 hard_fails)
- **Scope deviations:** none
- **Calibration:** Windows executor bash failure (sh not on PATH) — see escalation notes. `${PATH}` interpolation in `.mcp.json` env did not expand on Windows; fix needs full literal PATH or a different approach.
