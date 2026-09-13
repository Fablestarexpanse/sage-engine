"""
Achievement engine — counter bookkeeping and grant checks.

Two call shapes:
- record_counter(stats, registry, counter, delta): mutate a stats dict the
  caller already holds (single Redis write stays with the caller — combat).
- record_counter_for_player(player_id, counter, delta): read-modify-write for
  callers that don't otherwise touch stats (movement).

Both return the list of newly granted achievements so the caller can announce
them. Grants are recorded inside the stats blob under "achievements"
({id: {"granted_at": unix}}), so the existing PersistenceManager flush makes
them durable with no schema change.
"""

import logging
import time
from typing import Any

from sage.achievements.models import AchievementModel
from sage.achievements.registry import AchievementRegistry

logger = logging.getLogger(__name__)

COUNTERS_KEY = "counters"
GRANTS_KEY = "achievements"
VISITED_KEY = "visited_rooms"


def _ensure_blocks(stats: dict[str, Any]) -> None:
    if not isinstance(stats.get(COUNTERS_KEY), dict):
        stats[COUNTERS_KEY] = {}
    if not isinstance(stats.get(GRANTS_KEY), dict):
        stats[GRANTS_KEY] = {}


def _met(ach: AchievementModel, counters: dict[str, Any]) -> bool:
    checks = (int(counters.get(c, 0)) >= threshold for c, threshold in ach.criteria.items())
    return any(checks) if ach.match == "any" else all(checks)


def _check_grants(
    stats: dict[str, Any], registry: AchievementRegistry, counter: str
) -> list[AchievementModel]:
    granted: list[AchievementModel] = []
    for ach in registry.watching(counter):
        if ach.id in stats[GRANTS_KEY]:
            continue
        if _met(ach, stats[COUNTERS_KEY]):
            stats[GRANTS_KEY][ach.id] = {"granted_at": int(time.time())}
            granted.append(ach)
    return granted


def record_counter(
    stats: dict[str, Any],
    registry: AchievementRegistry,
    counter: str,
    delta: int = 1,
) -> list[AchievementModel]:
    """Adjust one counter on an in-hand stats dict; return newly granted achievements."""
    _ensure_blocks(stats)
    stats[COUNTERS_KEY][counter] = int(stats[COUNTERS_KEY].get(counter, 0)) + delta
    return _check_grants(stats, registry, counter)


def record_room_visit(
    stats: dict[str, Any],
    registry: AchievementRegistry,
    room_id: str,
) -> list[AchievementModel]:
    """Track unique rooms visited; bumps the rooms_visited counter on first visit only."""
    _ensure_blocks(stats)
    visited = stats.get(VISITED_KEY)
    if not isinstance(visited, list):
        visited = []
        stats[VISITED_KEY] = visited
    if room_id in visited:
        return []
    visited.append(room_id)
    stats[COUNTERS_KEY]["rooms_visited"] = len(visited)
    return _check_grants(stats, registry, "rooms_visited")


async def record_room_visit_for_player(player_id: str, room_id: str) -> list[AchievementModel]:
    """Read-modify-write variant for callers not already holding stats. Best-effort."""
    from sage.app import app_instance

    if app_instance is None:
        return []
    try:
        registry = app_instance.content_loader.get_achievement_registry()
        stats = await app_instance.redis.get_player_stats(player_id)
        before = len(stats.get(VISITED_KEY) or [])
        granted = record_room_visit(stats, registry, room_id)
        if len(stats[VISITED_KEY]) != before:
            await app_instance.redis.set_player_stats(player_id, stats)
        return granted
    except Exception as exc:
        logger.warning("Achievement room-visit tracking skipped: %s", exc)
        return []


def announcement(ach: AchievementModel) -> str:
    return f"*** Achievement unlocked ({ach.level}): {ach.story_line()} ***"
