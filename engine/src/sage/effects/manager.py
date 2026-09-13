"""
EffectsManager — advances player effects on the tick loop.

Players only for now: entity effects use the same engine but are processed
by whatever system applies them (none yet). Same accepted read-modify-write
pattern as field_gain_for_player: a concurrent command handler holding stats
across awaits can interleave; single-operator server, documented risk.
"""

import logging
from typing import TYPE_CHECKING

from sage.effects.engine import EFFECTS_KEY, process_effects

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)

EFFECT_CHECK_INTERVAL = 8  # 4 Hz tick → every 2 s


class EffectsManager:
    def __init__(self, server: "SageServer"):
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
        was_alive = int(stats.get("hp", 1)) > 0
        messages = process_effects(stats)
        if not messages and stats.get(EFFECTS_KEY):
            return  # nothing fired, nothing expired — skip the write
        session = self.server.session_manager.get_session_by_player(player_id)
        died = was_alive and int(stats.get("hp", 1)) <= 0
        granted = []
        if died:
            from sage.effects.death import record_player_death

            room_id = await self.server.redis.get_player_location(player_id)
            granted = await record_player_death(
                self.server, session, player_id, stats, room_id, "affliction"
            )
        await self.server.redis.set_player_stats(player_id, stats)

        if session is None:
            return
        for msg in messages:
            await session.send(f"\r\n{msg}")
        if granted:
            from sage.achievements.engine import announcement

            for ach in granted:
                await session.send(f"\r\n{announcement(ach)}")
        await self.server.push_character_snapshot(session)
        if int(stats.get("hp", 1)) <= 0:
            await session.end("died", "\r\nYou succumb to your afflictions. Disconnecting...")
