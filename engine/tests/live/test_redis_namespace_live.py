"""World namespaces on a real Redis: two worlds share a server, old keys are adopted once."""

from __future__ import annotations

import asyncio

import pytest

from sage.state.redis_client import RedisState
from sage.telemetry import heat, read_heatmaps
from tests.live.conftest import open_redis

pytestmark = pytest.mark.live


def _world(base: RedisState, namespace: str) -> RedisState:
    other = RedisState(base.config, namespace=namespace)
    other._client = base.client  # same connection, different namespace
    return other


def test_two_worlds_share_redis_without_seeing_each_other(live_config, monkeypatch):
    import sage.telemetry

    monkeypatch.setattr(sage.telemetry, "_disabled", False)  # heatmaps only; no log file

    async def go():
        async with open_redis(live_config) as raw:
            north, south = _world(raw, "north"), _world(raw, "south")
            await north.set_player_location("hero", "town:gate")
            await south.set_player_location("hero", "dock:pier")
            await heat(north, "kills", "town:gate")

            assert await north.get_player_location("hero") == "town:gate"
            assert await south.get_player_location("hero") == "dock:pier"
            assert await north.get_room_players("town:gate") == {"hero"}
            assert await south.get_room_players("town:gate") == set()
            assert await north.get_all_active_player_ids() == ["hero"]
            assert (await read_heatmaps(north, ["kills"]))["kills"] == {"town:gate": 1}
            assert (await read_heatmaps(south, ["kills"]))["kills"] == {}
            assert await raw.client.exists("north:player:hero:location")

    asyncio.run(go())


def test_pre_namespace_keys_are_adopted_once_and_never_clobber(live_config):
    async def go():
        async with open_redis(live_config) as raw:
            client = raw.client
            await client.set("player:hero:location", "town:gate")
            await client.hset("rentals", "town:loft", "hero")
            await client.set("unrelated:key", "stays")
            await client.set("world:player:taken:location", "new")
            await client.set("player:taken:location", "old")

            world = _world(raw, "world")
            moved = await world.adopt_unnamespaced({"player", "rentals"})

            assert moved == 2  # player:hero:location and rentals; the taken key is kept
            assert await world.get_player_location("hero") == "town:gate"
            assert await client.hget("world:rentals", "town:loft") == "hero"
            assert await client.get("unrelated:key") == "stays"
            assert await world.get_player_location("taken") == "new"
            assert await client.get("player:taken:location") == "old"
            assert await world.adopt_unnamespaced({"player", "rentals"}) == 0

    asyncio.run(go())
