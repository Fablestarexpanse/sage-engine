"""Integration: full dispatch → state mutation → session output, per command domain.

Uses the real CommandDispatcher and command registry with in-memory fakes for
Redis and content — no live services required.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

import sage.app as app_module
import sage.commands.combat as combat_mod

# Register all command modules on the global registry.
import sage.commands.communication
import sage.commands.info
import sage.commands.items
import sage.commands.movement
import sage.commands.proficiency  # noqa: F401
from sage.world.models import ExitModel, RoomModel
from tests.fakes import StubSession, make_fake_server

ROOM = "starter_zone:entrance"
ROOM_NORTH = "starter_zone:hall"


class IntegrationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = make_fake_server()
        self._saved = app_module.app_instance
        app_module.app_instance = self.server  # type: ignore[assignment]
        self.server.content_loader.rooms[ROOM] = RoomModel(
            id=ROOM,
            zone="starter_zone",
            type="chamber",
            description={"base": "The entrance chamber."},
            exits={"north": ExitModel(destination=ROOM_NORTH, description="A hallway.")},
        )
        self.server.content_loader.rooms[ROOM_NORTH] = RoomModel(
            id=ROOM_NORTH,
            zone="starter_zone",
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


class TestAttackIntegration(IntegrationCase):
    def test_attack_kill_flow(self) -> None:
        asyncio.run(self._attack_kill())

    async def _attack_kill(self) -> None:
        await self._login()
        await self.server.redis.set_entity_state(
            "stalker_1",
            {
                "name": "Void Stalker",
                "template": "stalker",
                "hp": 1,
                "max_hp": 10,
                "defense": 0,
                "alive": True,
                "loot": [],
            },
        )
        await self.server.redis.add_entity_to_room("stalker_1", ROOM)
        await self.server.dispatcher.dispatch(self.session, "attack stalker")
        self.assertIsNone(await self.server.redis.get_entity_state("stalker_1"))
        self.assertNotIn("stalker_1", await self.server.redis.get_room_entities(ROOM))


class TestFleeIntegration(IntegrationCase):
    def test_flee_success_flow(self) -> None:
        asyncio.run(self._flee_success())

    async def _flee_success(self) -> None:
        await self._login()
        await self.server.redis.set_entity_state("drone_1", {"name": "drone", "alive": True})
        await self.server.redis.add_entity_to_room("drone_1", ROOM)
        with mock.patch.object(combat_mod.random, "random", return_value=0.0):
            await self.server.dispatcher.dispatch(self.session, "flee")
        self.assertEqual(await self.server.redis.get_player_location("tester"), ROOM_NORTH)


class TestUnknownCommandIntegration(IntegrationCase):
    def test_unknown_verb(self) -> None:
        self._dispatch("xyzzy")
        self.assertTrue(any("xyzzy" in m for m in self.session.sent))


if __name__ == "__main__":
    unittest.main()


class TestKillEventIntegration(IntegrationCase):
    def test_kill_publishes_entity_killed_and_sends_subscriber_lines(self) -> None:
        asyncio.run(self._kill_event())

    async def _kill_event(self) -> None:
        from sage.core.events import EntityKilled, EventBus, RoomEntered

        self.server.events = EventBus()
        seen: list[EntityKilled] = []

        def on_kill(event: EntityKilled) -> None:
            seen.append(event)
            event.messages.append("The town will remember this.")

        entered: list[RoomEntered] = []
        self.server.events.subscribe(EntityKilled, on_kill, owner="probe")
        self.server.events.subscribe(RoomEntered, entered.append, owner="probe")
        await self._login()
        await self.server.redis.set_entity_state(
            "stalker_1",
            {
                "name": "Void Stalker",
                "template": "stalker",
                "hp": 1,
                "max_hp": 10,
                "defense": 0,
                "alive": True,
                "loot": [],
            },
        )
        await self.server.redis.add_entity_to_room("stalker_1", ROOM)
        await self.server.dispatcher.dispatch(self.session, "attack stalker")
        self.assertEqual(
            [(e.killer_id, e.template, e.room_id) for e in seen], [("tester", "stalker", ROOM)]
        )
        self.assertIn("The town will remember this.", "\n".join(self.session.sent))
        await self.server.dispatcher.dispatch(self.session, "north")
        self.assertEqual([(e.from_room_id, e.room_id) for e in entered], [(ROOM, ROOM_NORTH)])
