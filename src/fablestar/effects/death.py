"""Player death bookkeeping shared by every way a player can die."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def record_player_death(
    server, session, player_id: str, stats: dict[str, Any], room_id: str | None, cause: str
) -> list:
    """Count the death on the stats blob (caller saves it) and log telemetry.

    Agents keep their own death counter in AgentManager, so only telemetry is
    written for them here. Returns newly granted achievements.
    """
    from fablestar.telemetry import heat, log_event

    is_agent = bool(getattr(session, "is_agent", False))
    log_event("player_death", player=player_id, is_agent=is_agent, room=room_id or "", by=cause)
    if room_id:
        await heat(server.redis, "deaths", room_id)
    if is_agent:
        return []
    from fablestar.achievements.engine import COUNTERS_KEY, record_counter

    try:
        registry = server.content_loader.get_achievement_registry()
    except Exception:
        logger.debug("achievement registry unavailable; counting death only", exc_info=True)
        counters = stats.setdefault(COUNTERS_KEY, {})
        counters["deaths"] = int(counters.get("deaths", 0)) + 1
        return []
    return record_counter(stats, registry, "deaths")
