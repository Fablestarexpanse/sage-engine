"""Command handler unit tests — pure helpers and handler edge cases with fake state."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

import sage.app as app_module

# Importing the modules registers the commands on the global registry.
import sage.commands.combat as combat_mod
import sage.commands.communication
import sage.commands.info
import sage.commands.items
import sage.commands.movement  # noqa: F401
from sage.commands.combat import _roll_damage, attack, flee
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


class TestRollDamage(unittest.TestCase):
    def test_minimum_damage_is_one(self) -> None:
        with mock.patch("sage.commands.combat.random.randint", return_value=1):
            self.assertEqual(_roll_damage(1, 100), 1)

    def test_damage_formula(self) -> None:
        with mock.patch("sage.commands.combat.random.randint", return_value=4):
            self.assertEqual(_roll_damage(5, 2), 7)  # 5 + 4 - 2


class TestAttack(CommandTestCase):
    def test_no_args_prompts_usage(self) -> None:
        asyncio.run(self._no_args())

    async def _no_args(self) -> None:
        session = StubSession()
        await attack(session, [])  # type: ignore[arg-type]
        self.assertIn("Attack what?", session.sent[0])

    def test_unknown_target(self) -> None:
        asyncio.run(self._unknown_target())

    async def _unknown_target(self) -> None:
        await self.server.redis.set_player_location("tester", ROOM)
        session = StubSession()
        await attack(session, ["dragon"])  # type: ignore[arg-type]
        self.assertIn("no 'dragon' here", session.sent[-1])

    def test_kill_path_updates_state(self) -> None:
        asyncio.run(self._kill_path())

    async def _kill_path(self) -> None:
        await self.server.redis.set_player_location("tester", ROOM)
        await self.server.redis.set_player_stats("tester", {"hp": 20, "strength": 12})
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

        session = StubSession()
        await attack(session, ["stalker"])  # type: ignore[arg-type]

        # Entity is despawned by kill_entity after death
        self.assertIsNone(await self.server.redis.get_entity_state("stalker_1"))
        self.assertNotIn("stalker_1", await self.server.redis.get_room_entities(ROOM))
        self.assertTrue(any("dead" in m or "falls" in m for m in session.sent))
        self.assertFalse(session.closed)

    def test_wounded_entity_counterattacks(self) -> None:
        asyncio.run(self._wounded_counter())

    async def _wounded_counter(self) -> None:
        await self.server.redis.set_player_location("tester", ROOM)
        await self.server.redis.set_player_stats("tester", {"hp": 20})
        await self.server.redis.set_entity_state(
            "stalker_1",
            {
                "name": "Void Stalker",
                "template": "stalker",
                "hp": 100,
                "max_hp": 100,
                "defense": 0,
                "attack": 3,
                "alive": True,
                "loot": [],
            },
        )
        await self.server.redis.add_entity_to_room("stalker_1", ROOM)

        session = StubSession()
        await attack(session, ["stalker"])  # type: ignore[arg-type]

        state = await self.server.redis.get_entity_state("stalker_1")
        assert state is not None
        self.assertLess(state["hp"], 100)
        self.assertTrue(state["alive"])
        player = await self.server.redis.get_player_stats("tester")
        self.assertLess(player["hp"], 20)


class TestFlee(CommandTestCase):
    def _arm_room_with_exit(self) -> None:
        from sage.world.models import ExitModel

        self.server.content_loader.rooms[ROOM] = _room(
            exits={"north": ExitModel(destination=ROOM_NORTH, description="A door.")}
        )
        self.server.content_loader.rooms[ROOM_NORTH] = _room(ROOM_NORTH)

    async def _add_threat(self) -> None:
        await self.server.redis.set_entity_state("drone_1", {"name": "drone", "alive": True})
        await self.server.redis.add_entity_to_room("drone_1", ROOM)

    def test_flee_needs_a_threat(self) -> None:
        asyncio.run(self._flee_no_threat())

    async def _flee_no_threat(self) -> None:
        self._arm_room_with_exit()
        await self.server.redis.set_player_location("tester", ROOM)
        session = StubSession()
        await flee(session, [])  # type: ignore[arg-type]
        self.assertEqual(await self.server.redis.get_player_location("tester"), ROOM)
        self.assertTrue(any("nothing here to flee from" in m for m in session.sent))

    def test_flee_success_moves_player(self) -> None:
        asyncio.run(self._flee_success())

    async def _flee_success(self) -> None:
        self._arm_room_with_exit()
        await self.server.redis.set_player_location("tester", ROOM)
        await self._add_threat()
        session = StubSession()
        with mock.patch.object(combat_mod.random, "random", return_value=0.0):
            await flee(session, [])  # type: ignore[arg-type]
        self.assertEqual(await self.server.redis.get_player_location("tester"), ROOM_NORTH)
        self.assertTrue(any("You flee north" in m for m in session.sent))

    def test_flee_failure_stays_put(self) -> None:
        asyncio.run(self._flee_failure())

    async def _flee_failure(self) -> None:
        self._arm_room_with_exit()
        await self.server.redis.set_player_location("tester", ROOM)
        await self._add_threat()
        session = StubSession()
        with mock.patch.object(combat_mod.random, "random", return_value=0.9):
            await flee(session, [])  # type: ignore[arg-type]
        self.assertEqual(await self.server.redis.get_player_location("tester"), ROOM)
        self.assertTrue(any("fail to escape" in m for m in session.sent))

    def test_flee_nowhere_to_run(self) -> None:
        asyncio.run(self._flee_nowhere())

    async def _flee_nowhere(self) -> None:
        self.server.content_loader.rooms[ROOM] = _room()  # no exits
        await self.server.redis.set_player_location("tester", ROOM)
        await self._add_threat()
        session = StubSession()
        await flee(session, [])  # type: ignore[arg-type]
        self.assertTrue(any("nowhere to flee" in m for m in session.sent))


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
