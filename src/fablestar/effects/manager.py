"""
EffectsManager — advances player effects on the tick loop.

Players only for now: entity effects use the same engine but are processed
by whatever system applies them (none yet). Same accepted read-modify-write
pattern as field_gain_for_player: a concurrent command handler holding stats
across awaits can interleave; single-operator server, documented risk.
"""

import logging
from typing import TYPE_CHECKING

from fablestar.effects.engine import EFFECTS_KEY, process_effects

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)

EFFECT_CHECK_INTERVAL = 8  # 4 Hz tick → every 2 s


class EffectsManager:
    def __init__(self, server: "FablestarServer"):
        self.server = server

    async def on_tick(self, tick_count: int):
        if tick_count % EFFECT_CHECK_INTERVAL != 0:
            return
        for player_id in list(self.server.session_manager.player_to_session):
            try:
                await self._process_player(player_id)
            except Exception as exc:
                logger.warning("Effect processing failed for %s: %s", player_id, exc)

    async def _process_player(self, player_id: str):
        stats = await self.server.redis.get_player_stats(player_id)
        if not stats.get(EFFECTS_KEY):
            return
        messages = process_effects(stats)
        if not messages and stats.get(EFFECTS_KEY):
            return  # nothing fired, nothing expired — skip the write
        await self.server.redis.set_player_stats(player_id, stats)

        session = self.server.session_manager.get_session_by_player(player_id)
        if session is None:
            return
        for msg in messages:
            await session.send(f"\r\n{msg}")
        await self.server.push_character_snapshot(session)
        if int(stats.get("hp", 1)) <= 0:
            await session.send("\r\nYou succumb to your afflictions. Disconnecting...")
            await session.close()
