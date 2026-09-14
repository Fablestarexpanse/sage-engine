"""What the running server holds in Redis, for the Live world admin page.

Room player sets can hold names that are not connected: a crash skips the logout cleanup, and
before 2026-09-14 a staff move of an offline character added it too. Those names show up to
everyone in the room, so the snapshot reports them apart and ``clear_offline_occupants``
removes them. Every function scans the keyspace: fine for an admin view, not for game code.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Rows returned per list; totals are always counted in full.
DEFAULT_LIMIT = 500


def _connected(server: Any) -> dict[str, bool]:
    """Connected character name -> whether it is an agent (a virtual session)."""
    manager = server.session_manager
    out: dict[str, bool] = {}
    for name, session_id in list(manager.player_to_session.items()):
        session = manager.sessions.get(session_id)
        if session is not None:
            out[name] = bool(getattr(session, "virtual", False))
    return out


def _unavailable(error: str) -> dict[str, Any]:
    return {"redis_connected": False, "error": error, "rooms": [], "totals": {}}


async def world_live_snapshot(server: Any) -> dict[str, Any]:
    redis = server.redis
    if redis is None or not redis.is_connected:
        return _unavailable("Redis is not connected")
    try:
        occupied = await redis.scan_sets("room_players")
        floor = await redis.scan_sets("room_items")
        _, entity_states = await redis.scan_states("entity_state", 0)
        _, item_states = await redis.scan_states("item_state", 0)
    except Exception as exc:
        logger.debug("world live snapshot failed", exc_info=True)
        return _unavailable(str(exc))

    connected = _connected(server)
    rooms = []
    for room_id in sorted(set(occupied) | set(floor)):
        names = occupied.get(room_id, set())
        rooms.append(
            {
                "room_id": room_id,
                "players": sorted(n for n in names if connected.get(n) is False),
                "agents": sorted(n for n in names if connected.get(n) is True),
                "offline": sorted(n for n in names if n not in connected),
                "floor_items": len(floor.get(room_id, ())),
            }
        )
    return {
        "redis_connected": True,
        "rooms": rooms,
        "totals": {
            "rooms_with_players": sum(1 for r in rooms if r["players"]),
            "rooms_with_agents": sum(1 for r in rooms if r["agents"]),
            "offline_occupants": sum(len(r["offline"]) for r in rooms),
            "creatures": entity_states,
            "floor_items": sum(r["floor_items"] for r in rooms),
            "item_states": item_states,
        },
    }


async def clear_offline_occupants(server: Any) -> list[dict[str, str]]:
    """Take every name that is not connected out of the room player sets. Returns what went."""
    connected = _connected(server)
    removed = []
    for room_id, names in (await server.redis.scan_sets("room_players")).items():
        for name in sorted(names):
            if name not in connected:
                await server.redis.remove_player_from_room(name, room_id)
                removed.append({"room_id": room_id, "name": name})
    return removed


def _room_known(server: Any, room_id: str | None) -> bool:
    try:
        return bool(room_id) and server.content_loader.get_room(room_id) is not None
    except Exception:
        return False


async def live_creatures(server: Any, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Every live creature state, not only those in rooms someone is standing in."""
    states, total = await server.redis.scan_states("entity_state", limit)
    rows = [
        {**state, "room_known": _room_known(server, state.get("room_id"))}
        for state in sorted(states, key=lambda s: (str(s.get("room_id")), str(s.get("id"))))
    ]
    return {"rows": rows, "total": total}


async def floor_items(server: Any, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Items lying in rooms (room item sets), with their state."""
    rows: list[dict[str, Any]] = []
    total = 0
    for room_id, item_ids in sorted((await server.redis.scan_sets("room_items")).items()):
        for item_id in sorted(item_ids):
            total += 1
            if len(rows) >= limit:
                continue
            state = await server.redis.get_item_state(item_id) or {}
            rows.append(
                {
                    "id": item_id,
                    "room_id": room_id,
                    "template": state.get("template"),
                    "name": state.get("name"),
                    "has_state": bool(state),
                    "room_known": _room_known(server, room_id),
                }
            )
    return {"rows": rows, "total": total}


async def remove_floor_item(server: Any, room_id: str, item_id: str) -> bool:
    """Take an item off a room's floor and delete its state. False when it was not there."""
    if item_id not in await server.redis.get_room_items(room_id):
        return False
    await server.redis.remove_item_from_room(item_id, room_id)
    await server.redis.delete_item_state(item_id)
    return True
