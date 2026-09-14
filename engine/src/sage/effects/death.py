"""Player death bookkeeping shared by every way a player can die."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def record_player_death(
    server, session, player_id: str, stats: dict[str, Any], room_id: str | None, cause: str
) -> list:
    """Count the death on the stats blob (caller saves it) and log telemetry.

    Virtual sessions (automated characters) keep their own death counters, so only telemetry
    is written for them here. Returns the counter lines to show the player.
    """
    from sage.telemetry import heat, log_event

    virtual = bool(getattr(session, "virtual", False))
    log_event("player_death", player=player_id, virtual=virtual, room=room_id or "", by=cause)
    from sage.core.events import PlayerDied, emit

    await emit(
        server,
        PlayerDied(player_id=player_id, room_id=room_id, cause=cause, virtual=virtual, stats=stats),
    )
    if room_id:
        await heat(server.redis, "deaths", room_id)
    if virtual:
        return []
    from sage.world.counters import count

    return await count(server, player_id, stats, "deaths")
