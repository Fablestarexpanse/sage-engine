"""PersistenceManager flush cadence and ContentLoader cache invalidation."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from sage.state.persistence import PersistenceManager
from sage.world.loader import ContentLoader


class TestPersistenceOnTick(unittest.TestCase):
    def _manager_with_spy(self) -> tuple[PersistenceManager, list[int]]:
        pm = PersistenceManager(SimpleNamespace())  # type: ignore[arg-type]
        calls: list[int] = []

        async def spy() -> None:
            calls.append(1)

        pm.flush_all = spy  # type: ignore[method-assign]
        return pm, calls

    def test_flush_at_interval(self) -> None:
        asyncio.run(self._flush_at_interval())

    async def _flush_at_interval(self) -> None:
        pm, calls = self._manager_with_spy()
        await pm.on_tick(pm.flush_interval_ticks)
        self.assertEqual(len(calls), 1)

    def test_no_flush_between_intervals(self) -> None:
        asyncio.run(self._no_flush_between())

    async def _no_flush_between(self) -> None:
        pm, calls = self._manager_with_spy()
        await pm.on_tick(1)
        await pm.on_tick(pm.flush_interval_ticks - 1)
        await pm.on_tick(pm.flush_interval_ticks + 1)
        self.assertEqual(len(calls), 0)

    def test_flush_all_survives_redis_failure(self) -> None:
        asyncio.run(self._flush_survives())

    async def _flush_survives(self) -> None:
        class BrokenRedis:
            async def get_all_active_player_ids(self) -> list[str]:
                raise ConnectionError("redis down")

        pm = PersistenceManager(SimpleNamespace(redis=BrokenRedis()))  # type: ignore[arg-type]
        # Must not raise — errors are logged and the game loop continues.
        await pm.flush_all()


class TestContentLoaderInvalidate(unittest.TestCase):
    def test_room_eviction(self) -> None:
        loader = ContentLoader()
        key = loader._get_cache_key("room", "z1:r1")
        loader._cache[key] = object()
        loader.invalidate(Path("content/world/zones/z1/rooms/r1.yaml"))
        self.assertNotIn(key, loader._cache)

    def test_other_rooms_survive_room_eviction(self) -> None:
        loader = ContentLoader()
        stays = loader._get_cache_key("room", "z1:other")
        goes = loader._get_cache_key("room", "z1:r1")
        loader._cache[stays] = object()
        loader._cache[goes] = object()
        loader.invalidate(Path("content/world/zones/z1/rooms/r1.yaml"))
        self.assertIn(stays, loader._cache)
        self.assertNotIn(goes, loader._cache)

    def test_proficiency_eviction(self) -> None:
        loader = ContentLoader()
        loader._proficiency_cache._registry = object()  # type: ignore[assignment]
        loader.invalidate(Path("content/proficiencies/combat.yaml"))
        self.assertIsNone(loader._proficiency_cache._registry)

    def test_unknown_path_clears_everything(self) -> None:
        loader = ContentLoader()
        key = loader._get_cache_key("entity", "stalker")
        loader._cache[key] = object()
        loader.invalidate(Path("content/world/entities/stalker.yaml"))
        self.assertEqual(loader._cache, {})

    def test_clear_cache_resets_proficiency_registry(self) -> None:
        loader = ContentLoader()
        loader._cache["room:z1:r1"] = object()
        loader._proficiency_cache._registry = object()  # type: ignore[assignment]
        loader.clear_cache()
        self.assertEqual(loader._cache, {})
        self.assertIsNone(loader._proficiency_cache._registry)


if __name__ == "__main__":
    unittest.main()
