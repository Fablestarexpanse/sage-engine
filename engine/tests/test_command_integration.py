"""Integration: full dispatch → state mutation → session output, per command domain.

Uses the real CommandDispatcher and command registry with in-memory fakes for
Redis and content — no live services required.
"""

from __future__ import annotations

import asyncio
import unittest

import sage.app as app_module

# Register all command modules on the global registry.
from sage.world.models import ExitModel, RoomModel
from tests.fakes import StubSession, make_fake_server

ROOM = "testzone:entrance"
ROOM_NORTH = "testzone:hall"


class IntegrationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = make_fake_server()
        self._saved = app_module.app_instance
        app_module.app_instance = self.server  # type: ignore[assignment]
        self.server.content_loader.rooms[ROOM] = RoomModel(
            id=ROOM,
            zone="testzone",
            type="chamber",
            description={"base": "The entrance chamber."},
            exits={"north": ExitModel(destination=ROOM_NORTH, description="A hallway.")},
        )
        self.server.content_loader.rooms[ROOM_NORTH] = RoomModel(
            id=ROOM_NORTH,
            zone="testzone",
            type="corridor",
            description={"base": "A long hallway."},
            exits={"south": ExitModel(destination=ROOM, description="Back to the entrance.")},
        )
        self.session = StubSession()

    def tearDown(self) -> None:
        app_module.app_instance = self._saved

    async def _login(self) -> None:
        await self.server.redis.set_player_location("tester", ROOM)
        await self.server.redis.set_player_stats("tester", {"hp": 20})

    def _dispatch(self, line: str) -> None:
        asyncio.run(self._dispatch_async(line))

    async def _dispatch_async(self, line: str) -> None:
        await self._login()
        await self.server.dispatcher.dispatch(self.session, line)


class TestLookIntegration(IntegrationCase):
    def test_look_renders_room(self) -> None:
        self._dispatch("look")
        out = "\n".join(self.session.sent)
        self.assertIn(ROOM, out)
        self.assertIn("The entrance chamber.", out)
        self.assertIn("Exits: north", out)

    def test_alias_l(self) -> None:
        self._dispatch("l")
        self.assertIn("The entrance chamber.", "\n".join(self.session.sent))


class TestMovementIntegration(IntegrationCase):
    def test_move_north_updates_location_and_describes(self) -> None:
        self._dispatch("north")
        loc = asyncio.run(self.server.redis.get_player_location("tester"))
        self.assertEqual(loc, ROOM_NORTH)
        out = "\n".join(self.session.sent)
        self.assertIn("You move north.", out)
        self.assertIn("A long hallway.", out)

    def test_blocked_direction(self) -> None:
        self._dispatch("east")
        self.assertIn("cannot go east", "\n".join(self.session.sent))
        loc = asyncio.run(self.server.redis.get_player_location("tester"))
        self.assertEqual(loc, ROOM)


class TestUnknownCommandIntegration(IntegrationCase):
    def test_unknown_verb(self) -> None:
        self._dispatch("xyzzy")
        self.assertTrue(any("xyzzy" in m for m in self.session.sent))


if __name__ == "__main__":
    unittest.main()


class TestRoomEnteredIntegration(IntegrationCase):
    def test_moving_publishes_room_entered(self) -> None:
        asyncio.run(self._room_entered())

    async def _room_entered(self) -> None:
        from sage.core.events import EventBus, RoomEntered

        self.server.events = EventBus()
        entered: list[RoomEntered] = []
        self.server.events.subscribe(RoomEntered, entered.append, owner="probe")
        await self._login()
        await self.server.dispatcher.dispatch(self.session, "north")
        self.assertEqual([(e.from_room_id, e.room_id) for e in entered], [(ROOM, ROOM_NORTH)])
