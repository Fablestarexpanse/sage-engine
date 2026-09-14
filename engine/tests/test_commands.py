"""Command handler unit tests — handler edge cases with fake state (combat: plugins/combat)."""

from __future__ import annotations

import asyncio
import unittest

import sage.app as app_module

# Importing the modules registers the commands on the global registry.
import sage.commands.communication
import sage.commands.info
import sage.commands.items
import sage.commands.movement  # noqa: F401
from sage.commands.info import look
from sage.world.models import RoomModel
from tests.fakes import StubSession, make_fake_server

ROOM = "starter_zone:entrance"
ROOM_NORTH = "starter_zone:hall"


def _room(room_id: str = ROOM, exits: dict | None = None) -> RoomModel:
    return RoomModel(
        id=room_id,
        zone="starter_zone",
        type="chamber",
        description={"base": "A plain test chamber."},
        exits=exits or {},
    )


class CommandTestCase(unittest.TestCase):
    """Installs a fake app_instance around each test."""

    def setUp(self) -> None:
        self.server = make_fake_server()
        self._saved_instance = app_module.app_instance
        app_module.app_instance = self.server  # type: ignore[assignment]

    def tearDown(self) -> None:
        app_module.app_instance = self._saved_instance


class TestLook(CommandTestCase):
    def test_look_falls_back_to_base_description(self) -> None:
        asyncio.run(self._look_fallback())

    async def _look_fallback(self) -> None:
        self.server.content_loader.rooms[ROOM] = _room()
        await self.server.redis.set_player_location("tester", ROOM)
        session = StubSession()
        await look(session, [])  # type: ignore[arg-type]
        # No LLM configured on the fake server → base description fallback
        self.assertTrue(any("A plain test chamber." in m for m in session.sent))

    def test_look_shows_exits_and_entities(self) -> None:
        asyncio.run(self._look_exits_entities())

    async def _look_exits_entities(self) -> None:
        from sage.world.models import ExitModel

        self.server.content_loader.rooms[ROOM] = _room(
            exits={"north": ExitModel(destination=ROOM_NORTH, description="A door.")}
        )
        await self.server.redis.set_player_location("tester", ROOM)
        await self.server.redis.set_entity_state(
            "stalker_1", {"name": "Void Stalker", "alive": True}
        )
        await self.server.redis.add_entity_to_room("stalker_1", ROOM)
        session = StubSession()
        await look(session, [])  # type: ignore[arg-type]
        self.assertTrue(any("Exits: north" in m for m in session.sent))
        self.assertTrue(any("Void Stalker" in m for m in session.sent))

    def test_look_no_room(self) -> None:
        asyncio.run(self._look_no_room())

    async def _look_no_room(self) -> None:
        session = StubSession()
        await look(session, [])  # type: ignore[arg-type]
        self.assertTrue(any("lost in the void" in m for m in session.sent))

    def test_unauthenticated_rejected(self) -> None:
        asyncio.run(self._unauthenticated())

    async def _unauthenticated(self) -> None:
        session = StubSession(player_id=None)
        await look(session, [])  # type: ignore[arg-type]
        self.assertTrue(any("Not authenticated" in m for m in session.sent))


if __name__ == "__main__":
    unittest.main()
