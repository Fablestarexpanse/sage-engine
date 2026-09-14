"""
AmbientManager — periodic room atmosphere lines (Epitaph-style room chats).

Runs on the tick loop like EntitySpawnManager and, like it, only looks at
rooms that currently hold players. Each occupied room with an `ambient:`
block gets a random line every min_interval..max_interval seconds; motion
belongs here, never in static descriptions (docs/design/EPITAPH_LESSONS.md).
"""

import logging
import random
import time
from typing import TYPE_CHECKING

from sage.world.models import AmbientModel

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)

# 4 Hz tick → check every 8 ticks = 2 s; cheap because occupied rooms only.
AMBIENT_CHECK_INTERVAL = 8


def pick_line(ambient: AmbientModel, last_line: str | None, rng: random.Random) -> str:
    """Random line, avoiding an immediate repeat when there is a choice."""
    pool = [line for line in ambient.lines if line != last_line]
    return rng.choice(pool or ambient.lines)


def next_due(ambient: AmbientModel, now: float, rng: random.Random) -> float:
    lo, hi = sorted((ambient.min_interval, ambient.max_interval))
    return now + rng.uniform(lo, hi)


class AmbientManager:
    def __init__(self, server: "SageServer", rng: random.Random | None = None):
        self.server = server
        self.rng = rng or random.Random()
        # room_id -> monotonic timestamp when the next line is due
        self._due: dict[str, float] = {}
        self._last_line: dict[str, str] = {}

    async def on_tick(self, tick_count: int):
        if tick_count % AMBIENT_CHECK_INTERVAL != 0:
            return

        occupied: dict[str, list[str]] = {}
        for player_id in list(self.server.session_manager.player_to_session):
            room_id = await self.server.redis.get_player_location(player_id)
            if room_id:
                occupied.setdefault(room_id, []).append(player_id)

        # Forget timers for rooms everyone has left, so re-entry re-rolls.
        for room_id in list(self._due):
            if room_id not in occupied:
                del self._due[room_id]
                self._last_line.pop(room_id, None)

        now = time.monotonic()
        for room_id, player_ids in occupied.items():
            room = self.server.content_loader.get_room(room_id)
            if not room or not room.ambient:
                continue
            due = self._due.get(room_id)
            if due is None:
                # First sighting: schedule ahead rather than firing on entry.
                self._due[room_id] = next_due(room.ambient, now, self.rng)
                continue
            if now < due:
                continue
            line = pick_line(room.ambient, self._last_line.get(room_id), self.rng)
            self._last_line[room_id] = line
            self._due[room_id] = next_due(room.ambient, now, self.rng)
            for player_id in player_ids:
                session = self.server.session_manager.get_session_by_player(player_id)
                if session:
                    try:
                        await session.send(f"\r\n{line}")
                    except Exception as exc:
                        logger.debug("Ambient send failed for %s: %s", player_id, exc)
