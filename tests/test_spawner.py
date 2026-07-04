"""EntitySpawnManager — spawn, despawn, kill, and loot drops."""

from __future__ import annotations

import asyncio
import random
import unittest

from fablestar.world.models import EntityTemplate, ItemTemplate
from fablestar.world.spawner import EntitySpawnManager
from tests.fakes import make_fake_server

ROOM = "starter_zone:entrance"


def _stalker() -> EntityTemplate:
    return EntityTemplate(
        id="stalker",
        name="Void Stalker",
        stats={"hp": 12, "max_hp": 12, "attack": 4, "defense": 2},
        loot=["resonance_shard"],
    )


def _shard() -> ItemTemplate:
    return ItemTemplate(id="resonance_shard", name="Resonance Shard", value=25, weight=0.2)


class TestSpawner(unittest.TestCase):
    def setUp(self) -> None:
        self.server = make_fake_server()
        self.server.content_loader.entity_templates["stalker"] = _stalker()
        self.server.content_loader.item_templates["resonance_shard"] = _shard()
        self.spawner = EntitySpawnManager(self.server)  # type: ignore[arg-type]

    def test_spawn_entity_writes_state_and_room(self) -> None:
        asyncio.run(self._spawn_writes())

    async def _spawn_writes(self) -> None:
        eid = await self.spawner.spawn_entity(ROOM, "stalker")
        assert eid is not None
        state = await self.server.redis.get_entity_state(eid)
        assert state is not None
        self.assertEqual(state["template"], "stalker")
        self.assertEqual(state["hp"], 12)
        self.assertEqual(state["attack"], 4)
        self.assertTrue(state["alive"])
        self.assertIn(eid, await self.server.redis.get_room_entities(ROOM))

    def test_spawn_unknown_template_returns_none(self) -> None:
        asyncio.run(self._spawn_unknown())

    async def _spawn_unknown(self) -> None:
        self.assertIsNone(await self.spawner.spawn_entity(ROOM, "nonexistent"))

    def test_despawn_removes_everything(self) -> None:
        asyncio.run(self._despawn_removes())

    async def _despawn_removes(self) -> None:
        eid = await self.spawner.spawn_entity(ROOM, "stalker")
        assert eid is not None
        await self.spawner.despawn_entity(eid, ROOM)
        self.assertIsNone(await self.server.redis.get_entity_state(eid))
        self.assertNotIn(eid, await self.server.redis.get_room_entities(ROOM))

    def test_kill_entity_drops_all_loot_when_rng_low(self) -> None:
        asyncio.run(self._kill_drops())

    async def _kill_drops(self) -> None:
        eid = await self.spawner.spawn_entity(ROOM, "stalker")
        assert eid is not None
        orig = random.random
        random.random = lambda: 0.0  # always under the 60% drop chance
        try:
            dropped = await self.spawner.kill_entity(eid, ROOM)
        finally:
            random.random = orig
        self.assertEqual(len(dropped), 1)
        floor = await self.server.redis.get_room_items(ROOM)
        self.assertEqual(set(dropped), floor)
        istate = await self.server.redis.get_item_state(dropped[0])
        assert istate is not None
        self.assertEqual(istate["template"], "resonance_shard")
        # Entity fully despawned afterwards
        self.assertIsNone(await self.server.redis.get_entity_state(eid))

    def test_kill_entity_no_drops_when_rng_high(self) -> None:
        asyncio.run(self._kill_no_drops())

    async def _kill_no_drops(self) -> None:
        eid = await self.spawner.spawn_entity(ROOM, "stalker")
        assert eid is not None
        orig = random.random
        random.random = lambda: 1.0  # never under the drop chance
        try:
            dropped = await self.spawner.kill_entity(eid, ROOM)
        finally:
            random.random = orig
        self.assertEqual(dropped, [])
        self.assertEqual(await self.server.redis.get_room_items(ROOM), set())

    def test_kill_missing_entity_returns_empty(self) -> None:
        asyncio.run(self._kill_missing())

    async def _kill_missing(self) -> None:
        self.assertEqual(await self.spawner.kill_entity("ghost_123", ROOM), [])


if __name__ == "__main__":
    unittest.main()
