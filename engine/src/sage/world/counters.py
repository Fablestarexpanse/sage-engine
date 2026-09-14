"""Per-character counters: generic bookkeeping any world or plugin can read.

The engine counts what happens (kills, deaths, trades, rooms visited…) in the character's stats
blob under ``counters`` and publishes :class:`CountersChanged`. What a world *does* with a count
— achievements, titles, quests — is a plugin subscribing to that event and adding lines the
caller sends to the player.
"""

from __future__ import annotations

import logging
from typing import Any

from sage.core.events import CountersChanged, emit

logger = logging.getLogger(__name__)

COUNTERS_KEY = "counters"
VISITED_KEY = "visited_rooms"
ROOMS_VISITED = "rooms_visited"


def counters(stats: dict[str, Any]) -> dict[str, int]:
    block = stats.get(COUNTERS_KEY)
    if not isinstance(block, dict):
        block = {}
        stats[COUNTERS_KEY] = block
    return block


def bump(stats: dict[str, Any], name: str, delta: int = 1) -> int:
    block = counters(stats)
    block[name] = int(block.get(name, 0)) + delta
    return block[name]


def note_visit(stats: dict[str, Any], room_id: str) -> bool:
    """Record a room as visited; True (and rooms_visited bumped) only on the first visit."""
    visited = stats.get(VISITED_KEY)
    if not isinstance(visited, list):
        visited = []
        stats[VISITED_KEY] = visited
    if room_id in visited:
        return False
    visited.append(room_id)
    counters(stats)[ROOMS_VISITED] = len(visited)
    return True


async def count(
    server: Any, player_id: str, stats: dict[str, Any], *names: str, delta: int = 1
) -> list[str]:
    """Bump counters on a stats blob the caller holds (and saves); return lines to show."""
    names = tuple(n for n in names if n)
    if not names:
        return []
    for name in names:
        bump(stats, name, delta)
    event = CountersChanged(player_id=player_id, counters=list(names), stats=stats)
    await emit(server, event)
    return event.messages


async def count_for_player(server: Any, player_id: str, *names: str, delta: int = 1) -> list[str]:
    """Read-modify-write variant for callers that don't already hold the stats blob."""
    try:
        stats = await server.redis.get_player_stats(player_id)
        lines = await count(server, player_id, stats, *names, delta=delta)
        await server.redis.set_player_stats(player_id, stats)
        return lines
    except Exception:
        logger.warning("Counter update skipped for %s: %s", player_id, names, exc_info=True)
        return []


async def visit_for_player(server: Any, player_id: str, room_id: str) -> list[str]:
    """Track a room visit; publishes rooms_visited only when the room is new to the player."""
    try:
        stats = await server.redis.get_player_stats(player_id)
        if not note_visit(stats, room_id):
            return []
        event = CountersChanged(player_id=player_id, counters=[ROOMS_VISITED], stats=stats)
        await emit(server, event)
        await server.redis.set_player_stats(player_id, stats)
        return event.messages
    except Exception:
        logger.warning("Room visit tracking skipped for %s", player_id, exc_info=True)
        return []
