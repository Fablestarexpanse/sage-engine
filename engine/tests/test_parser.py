"""Parser pipeline tests — tokenizer, registry, and dispatcher."""

from __future__ import annotations

import asyncio
import unittest

from sage.commands.registry import CommandRegistry, registry
from sage.parser.dispatcher import CommandDispatcher
from sage.parser.tokenizer import tokenize


class _StubSession:
    """Minimal duck-type Session for hermetic dispatcher tests."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def say(self, key: str, **variables) -> None:
        from sage import lexicon

        self.sent.append(lexicon.t(key, **variables))


# ---------------------------------------------------------------------------
# TestTokenize
# ---------------------------------------------------------------------------


class TestTokenize(unittest.TestCase):
    """Tests for sage.parser.tokenizer.tokenize()."""

    def test_empty_string_returns_empty_list(self) -> None:
        self.assertEqual(tokenize(""), [])

    def test_whitespace_only_returns_empty_list(self) -> None:
        self.assertEqual(tokenize("  "), [])

    def test_splits_on_spaces(self) -> None:
        self.assertEqual(tokenize("go north"), ["go", "north"])

    def test_lowercases_tokens(self) -> None:
        self.assertEqual(tokenize("GO NORTH"), ["go", "north"])

    def test_quoted_string_is_single_token(self) -> None:
        self.assertEqual(tokenize('say "hello world"'), ["say", "hello world"])

    def test_unquoted_multi_word_is_three_tokens(self) -> None:
        self.assertEqual(tokenize("say hello world"), ["say", "hello", "world"])

    def test_malformed_quote_falls_back_to_split(self) -> None:
        # Malformed quote triggers ValueError → fallback .split() path
        result = tokenize("cmd 'it\\'s broken")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)


# ---------------------------------------------------------------------------
# TestCommandRegistry
# ---------------------------------------------------------------------------


class TestCommandRegistry(unittest.TestCase):
    """Tests for sage.commands.registry.CommandRegistry."""

    def setUp(self) -> None:
        self.reg = CommandRegistry()

        async def _noop(session, args):
            pass

        self.handler = _noop

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.reg.get("missing"))

    def test_register_and_get_by_name(self) -> None:
        self.reg.register("look", self.handler)
        cmd = self.reg.get("look")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.name, "look")
        self.assertIs(cmd.handler, self.handler)

    def test_get_by_alias(self) -> None:
        self.reg.register("go", self.handler, aliases=["move", "walk"])
        cmd = self.reg.get("move")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.name, "go")

    def test_all_aliases_resolve(self) -> None:
        self.reg.register("go", self.handler, aliases=["move", "walk"])
        go_cmd = self.reg.get("go")
        move_cmd = self.reg.get("move")
        walk_cmd = self.reg.get("walk")
        self.assertIs(go_cmd, move_cmd)
        self.assertIs(move_cmd, walk_cmd)

    def test_non_alias_returns_none(self) -> None:
        self.reg.register("go", self.handler, aliases=["move", "walk"])
        self.assertIsNone(self.reg.get("run"))

    def test_no_aliases_defaults_to_empty_list(self) -> None:
        self.reg.register("look", self.handler)
        cmd = self.reg.get("look")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.aliases, [])


# ---------------------------------------------------------------------------
# TestCommandDispatcher
# ---------------------------------------------------------------------------


class TestCommandDispatcher(unittest.TestCase):
    """Tests for sage.parser.dispatcher.CommandDispatcher.dispatch()."""

    def setUp(self) -> None:
        self.dispatcher = CommandDispatcher()
        self._commands_snapshot = dict(registry._commands)
        self._aliases_snapshot = dict(registry._aliases)

    def tearDown(self) -> None:
        registry._commands.clear()
        registry._commands.update(self._commands_snapshot)
        registry._aliases.clear()
        registry._aliases.update(self._aliases_snapshot)

    def test_empty_input_sends_nothing(self) -> None:
        asyncio.run(self._empty_input())

    async def _empty_input(self) -> None:
        session = _StubSession()
        await self.dispatcher.dispatch(session, "")
        self.assertEqual(session.sent, [])

    def test_whitespace_input_sends_nothing(self) -> None:
        asyncio.run(self._whitespace_input())

    async def _whitespace_input(self) -> None:
        session = _StubSession()
        await self.dispatcher.dispatch(session, "   ")
        self.assertEqual(session.sent, [])

    def test_unknown_command_sends_error(self) -> None:
        asyncio.run(self._unknown_command())

    async def _unknown_command(self) -> None:
        session = _StubSession()
        await self.dispatcher.dispatch(session, "xyzzy")
        self.assertTrue(len(session.sent) >= 1)
        self.assertIn("xyzzy", session.sent[0])

    def test_known_command_calls_handler_with_args(self) -> None:
        asyncio.run(self._known_command())

    async def _known_command(self) -> None:
        captured: dict[str, list[str]] = {}

        async def _capture(session, args):
            captured["args"] = args

        registry.register("ping", _capture)
        session = _StubSession()
        await self.dispatcher.dispatch(session, "ping foo bar")
        self.assertEqual(captured.get("args"), ["foo", "bar"])


if __name__ == "__main__":
    unittest.main()
