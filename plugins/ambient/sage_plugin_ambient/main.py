"""
Ambient plugin — periodic room atmosphere lines.

Only rooms that currently hold connected characters are considered. Each occupied room with an
`ambient:` block gets a random line every min_interval..max_interval seconds; motion belongs here,
never in static descriptions.
"""

from __future__ import annotations

import logging
import random
import time

from pydantic import BaseModel, Field

from sage.api import PluginAPI

logger = logging.getLogger(__name__)

CHECK_SECONDS = 2.0  # cheap: occupied rooms only


class AmbientModel(BaseModel):
    """`ambient:` — occasional atmosphere lines shown to characters in the room."""

    lines: list[str] = Field(min_length=1)
    min_interval: float = Field(default=45.0, gt=0)
    max_interval: float = Field(default=120.0, gt=0)


def pick_line(ambient: AmbientModel, last_line: str | None, rng: random.Random) -> str:
    """Random line, avoiding an immediate repeat when there is a choice."""
    pool = [line for line in ambient.lines if line != last_line]
    return rng.choice(pool or ambient.lines)


def next_due(ambient: AmbientModel, now: float, rng: random.Random) -> float:
    lo, hi = sorted((ambient.min_interval, ambient.max_interval))
    return now + rng.uniform(lo, hi)


class AmbientDirector:
    def __init__(self, api: PluginAPI, rng: random.Random | None = None):
        self.api = api
        self.rng = rng or random.Random()
        # room_id -> monotonic timestamp when the next line is due
        self._due: dict[str, float] = {}
        self._last_line: dict[str, str] = {}

    async def on_check(self, tick: int) -> None:
        occupied: dict[str, list[str]] = {}
        for player_id in self.api.sessions.online():
            room_id = await self.api.state.location(player_id)
            if room_id:
                occupied.setdefault(room_id, []).append(player_id)

        # Forget timers for rooms everyone has left, so re-entry re-rolls.
        for room_id in list(self._due):
            if room_id not in occupied:
                del self._due[room_id]
                self._last_line.pop(room_id, None)

        now = time.monotonic()
        for room_id, player_ids in occupied.items():
            room = self.api.content.room(room_id)
            ambient = self.api.content.extension(room, "room", "ambient") if room else None
            if ambient is None:
                continue
            due = self._due.get(room_id)
            if due is None:
                # First sighting: schedule ahead rather than firing on entry.
                self._due[room_id] = next_due(ambient, now, self.rng)
                continue
            if now < due:
                continue
            line = pick_line(ambient, self._last_line.get(room_id), self.rng)
            self._last_line[room_id] = line
            self._due[room_id] = next_due(ambient, now, self.rng)
            for player_id in player_ids:
                session = self.api.sessions.get(player_id)
                if session:
                    try:
                        await session.send(line)
                    except Exception as exc:
                        logger.debug("Ambient send failed for %s: %s", player_id, exc)


def setup(api: PluginAPI) -> None:
    api.content.extend("room", "ambient", AmbientModel)
    api.tick.every(CHECK_SECONDS, AmbientDirector(api).on_check, name="ambient")
