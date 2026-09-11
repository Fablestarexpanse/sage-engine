"""Combat LLM narration contract — the golden rule's concrete implementation.

Deterministic code decides the outcome; the LLM only colours the text. These
tests exercise both branches deliberately: narration text reaches the player
when the LLM succeeds, and the plain-text fallback fires when narration setup
raises — in both cases the deterministic kill still happens.
"""

import asyncio
import unittest
from types import SimpleNamespace

import fablestar.commands.combat  # noqa: F401 — registers the attack command
from fablestar import app as app_module
from tests.fakes import StubSession, make_fake_server

STALKER = {
    "name": "Void Stalker",
    "template": "stalker",
    "hp": 1,
    "max_hp": 10,
    "defense": 0,
    "alive": True,
    "loot": [],
}
ROOM = "starter_zone:entrance"


class _FakeLLM:
    async def generate(self, prompt: str, max_tokens: int = 250) -> str:
        return "The stalker crumples in a spray of static."


class _FakePrompts:
    def render(self, name: str, **ctx) -> str:
        return f"[{name}]"


class _ExplodingPrompts:
    def render(self, name: str, **ctx) -> str:
        raise RuntimeError("template missing")


class NarrationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = make_fake_server()
        self._saved = app_module.app_instance
        app_module.app_instance = self.server  # type: ignore[assignment]
        self.session = StubSession()

    def tearDown(self) -> None:
        app_module.app_instance = self._saved

    async def _kill_stalker(self) -> None:
        await self.server.redis.set_player_location("tester", ROOM)
        await self.server.redis.set_player_stats("tester", {"hp": 20})
        await self.server.redis.set_entity_state("stalker_1", dict(STALKER))
        await self.server.redis.add_entity_to_room("stalker_1", ROOM)
        await self.server.dispatcher.dispatch(self.session, "attack stalker")

    def test_llm_narration_reaches_player(self) -> None:
        self.server.llm_client = _FakeLLM()
        self.server.prompt_manager = _FakePrompts()
        asyncio.run(self._kill_stalker())
        joined = "\n".join(self.session.sent)
        self.assertIn("The stalker crumples in a spray of static.", joined)
        # deterministic outcome regardless of narration
        self.assertIn("Void Stalker is dead.", joined)

    def test_fallback_when_narration_setup_raises(self) -> None:
        self.server.llm_client = SimpleNamespace()  # no generate attr needed — render raises first
        self.server.prompt_manager = _ExplodingPrompts()
        asyncio.run(self._kill_stalker())
        joined = "\n".join(self.session.sent)
        self.assertIn("You strike Void Stalker for", joined)
        self.assertIn("It falls.", joined)
        self.assertIn("Void Stalker is dead.", joined)


if __name__ == "__main__":
    unittest.main()
