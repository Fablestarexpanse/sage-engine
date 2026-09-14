"""The Live world admin view counts what is really there: connected players, agents, names left
behind in room sets, every live creature and every item on a floor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sage.admin import character_tools, world_live
from tests.fakes import make_fake_server


def _server_with_sessions(**connected: bool):
    """connected: character name -> True for an agent, False for a human session."""
    server = make_fake_server()
    sessions = {f"s-{name}": SimpleNamespace(virtual=agent) for name, agent in connected.items()}
    server.session_manager = SimpleNamespace(
        sessions=sessions,
        player_to_session={name: f"s-{name}" for name in connected},
        get_session_by_player=lambda name: sessions.get(f"s-{name}"),
    )
    return server


def test_snapshot_tells_players_agents_and_left_behind_names_apart():
    server = _server_with_sessions(Ann=False, Sela=True)
    redis = server.redis
    redis.room_players = {
        "town:inn": {"Ann", "Sela", "Gone"},
        "town:gate": {"Sela"},
        "town:well": set(),
    }
    redis.room_items = {"town:gate": {"bread_1", "bread_2"}}
    redis.entity_states = {"rat_1": {"id": "rat_1", "room_id": "town:cellar"}}

    snap = asyncio.run(world_live.world_live_snapshot(server))

    inn = next(r for r in snap["rooms"] if r["room_id"] == "town:inn")
    assert (inn["players"], inn["agents"], inn["offline"]) == (["Ann"], ["Sela"], ["Gone"])
    assert "town:well" not in {r["room_id"] for r in snap["rooms"]}
    assert snap["totals"] == {
        "rooms_with_players": 1,
        "rooms_with_agents": 2,
        "offline_occupants": 1,
        "creatures": 1,
        "floor_items": 2,
        "item_states": 0,
    }


def test_clear_offline_removes_only_names_that_are_not_connected():
    server = _server_with_sessions(Ann=False, Sela=True)
    server.redis.room_players = {"town:inn": {"Ann", "Sela", "Gone"}}
    removed = asyncio.run(world_live.clear_offline_occupants(server))
    assert removed == [{"room_id": "town:inn", "name": "Gone"}]
    assert server.redis.room_players["town:inn"] == {"Ann", "Sela"}


def test_every_creature_is_listed_even_where_nobody_stands():
    server = _server_with_sessions()
    server.content_loader.rooms = {"town:cellar": object()}
    server.redis.entity_states = {
        "rat_1": {"id": "rat_1", "room_id": "town:cellar"},
        "drone_1": {"id": "drone_1", "room_id": "old_zone:bay"},
    }
    result = asyncio.run(world_live.live_creatures(server, limit=1))
    assert result["total"] == 2 and len(result["rows"]) == 1
    rows = asyncio.run(world_live.live_creatures(server))["rows"]
    assert {(r["id"], r["room_known"]) for r in rows} == {("rat_1", True), ("drone_1", False)}


def test_floor_items_list_and_remove():
    server = _server_with_sessions()
    redis = server.redis
    redis.room_items = {"town:gate": {"bread_1"}}
    redis.item_states = {"bread_1": {"id": "bread_1", "template": "bread_loaf", "name": "bread"}}
    rows = asyncio.run(world_live.floor_items(server))["rows"]
    assert rows == [
        {
            "id": "bread_1",
            "room_id": "town:gate",
            "template": "bread_loaf",
            "name": "bread",
            "has_state": True,
            "room_known": False,
        }
    ]
    assert asyncio.run(world_live.remove_floor_item(server, "town:inn", "bread_1")) is False
    assert asyncio.run(world_live.remove_floor_item(server, "town:gate", "bread_1")) is True
    assert not redis.room_items["town:gate"] and "bread_1" not in redis.item_states


def test_staff_move_of_an_offline_character_does_not_put_it_in_the_room():
    server = _server_with_sessions(Ann=False)
    redis = server.redis
    redis.locations = {"Gone": "town:inn", "Ann": "town:inn"}
    redis.room_players = {"town:inn": {"Ann"}}

    asyncio.run(character_tools._relocate(server, "Gone", "town:gate"))
    asyncio.run(character_tools._relocate(server, "Ann", "town:gate"))

    assert redis.locations == {"Gone": "town:gate", "Ann": "town:gate"}
    assert redis.room_players["town:gate"] == {"Ann"}
    assert redis.room_players["town:inn"] == set()
