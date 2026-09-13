"""The factions plugin through the real host: kills, contracts, payouts and its state seal."""

from __future__ import annotations

import asyncio

import pytest

from sage.core.events import EntityKilled
from sage.plugins.manifest import PluginError
from tests.fakes import StubSession, repo_world


def _kill_mission(target: str, count: int = 1) -> dict:
    return {
        "faction": "dockworkers",
        "kind": "kill",
        "target": target,
        "count": count,
        "progress": 0,
    }


def test_kill_moves_reputation_mission_wallet_and_counters(plugin_host):
    host = plugin_host(repo_world(), ["achievements", "factions"])
    stats: dict = {"mission": _kill_mission("scrap_drone"), host.world.currencies[0].key: 0}
    event = EntityKilled(
        killer_id="hero", entity_id="e1", template="scrap_drone", room_id="z:r", stats=stats
    )
    asyncio.run(host.events.publish(event))

    assert stats["factions"]["dockworkers"] > 0
    assert stats["mission"] is None
    assert stats[host.world.currencies[0].key] > 0
    assert stats["counters"]["missions_completed"] == 1
    assert any(line.startswith("Mission complete") for line in event.messages), event.messages


def test_collect_contract_completes_through_the_command(plugin_host):
    host = plugin_host(repo_world(), ["factions"])
    key = host.world.currencies[0].key
    host.redis.stats["hero"] = {
        "mission": {
            "faction": "salvage_union",
            "kind": "collect",
            "target": "power_cell",
            "count": 2,
            "progress": 0,
        },
        key: 1,
        "hp": 10,
    }
    host.redis.inventories["hero"] = [
        {"id": "a", "template": "power_cell"},
        {"id": "b", "template": "power_cell"},
        {"id": "c", "template": "rope"},
    ]
    session = StubSession("hero")
    handler = host.registry.get("missions").handler
    asyncio.run(handler(session, ["complete"]))

    saved = host.redis.stats["hero"]
    assert saved["mission"] is None
    assert saved[key] > 1 and saved["hp"] == 10
    assert saved["counters"]["missions_completed"] == 1
    assert [it["id"] for it in host.redis.inventories["hero"]] == ["c"]
    assert "Mission complete" in session.sent[-1]


def test_state_edit_refuses_keys_the_plugin_does_not_own(plugin_host):
    host = plugin_host(repo_world(), ["factions"])
    api = next(r.api for r in host.loaded if r.id == "factions")
    host.redis.stats["hero"] = {"hp": 10}

    async def scribble():
        async with api.state.edit("hero") as stats:
            stats["hp"] = 999

    with pytest.raises(PluginError, match="does not own"):
        asyncio.run(scribble())
    assert host.redis.stats["hero"]["hp"] == 10


def test_worlds_without_the_plugin_have_no_faction_commands(plugin_host):
    host = plugin_host(repo_world(), ["achievements"])
    assert host.registry.get("missions") is None and host.registry.get("factions") is None
