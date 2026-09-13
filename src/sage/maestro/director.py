"""
MaestroDirector — picks on players when it gets bored.

Every check window it considers each connected player: if their personal
cooldown has lapsed, it roulette-selects among applicable event modules —
with a heavy "nothing happens" weight, because dread needs silence between
notes. Runs on the tick loop like the spawner and ambient managers.
"""

import logging
import random
import time
from typing import TYPE_CHECKING, Any

from sage.maestro.modules import MODULES

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)

MAESTRO_CHECK_INTERVAL = 120  # 4 Hz tick → consider players every 30 s
COOLDOWN_RANGE_S = (90.0, 240.0)  # min silence per player after any firing
NOTHING_WEIGHT = 60  # vs typical module interests of 2-15


def pick_module(
    modules: list[dict[str, Any]],
    ctx: dict[str, Any],
    rng: random.Random,
    nothing_weight: int = NOTHING_WEIGHT,
) -> dict[str, Any] | None:
    """Roulette selection over module interests plus a do-nothing slot."""
    weighted: list[tuple[dict[str, Any] | None, int]] = [(None, max(0, nothing_weight))]
    for mod in modules:
        try:
            w = int(mod["interest"](ctx))
        except Exception as exc:
            logger.warning("Maestro module %s interest failed: %s", mod.get("name"), exc)
            continue
        if w > 0:
            weighted.append((mod, w))
    total = sum(w for _, w in weighted)
    if total <= 0:
        return None
    roll = rng.uniform(0, total)
    acc = 0.0
    for mod, w in weighted:
        acc += w
        if roll <= acc:
            return mod
    return None


class MaestroDirector:
    def __init__(self, server: "SageServer", rng: random.Random | None = None):
        self.server = server
        self.rng = rng or random.Random()
        self._next_ok: dict[str, float] = {}  # player_id -> monotonic time

    def _eligible(self, player_id: str, now: float) -> bool:
        return now >= self._next_ok.get(player_id, 0.0)

    def _set_cooldown(self, player_id: str, now: float) -> None:
        lo, hi = COOLDOWN_RANGE_S
        self._next_ok[player_id] = now + self.rng.uniform(lo, hi)

    async def on_tick(self, tick_count: int):
        if tick_count % MAESTRO_CHECK_INTERVAL != 0:
            return
        now = time.monotonic()
        for player_id in list(self.server.session_manager.player_to_session):
            try:
                await self._consider(player_id, now)
            except Exception as exc:
                logger.warning("Maestro consider failed for %s: %s", player_id, exc)
        # Forget cooldowns of players long gone.
        active = set(self.server.session_manager.player_to_session)
        for pid in list(self._next_ok):
            if pid not in active:
                del self._next_ok[pid]

    async def _consider(self, player_id: str, now: float):
        if not self._eligible(player_id, now):
            return
        session = self.server.session_manager.get_session_by_player(player_id)
        if session is None:
            return
        room_id = await self.server.redis.get_player_location(player_id)
        if not room_id:
            return
        ctx = {
            "player_id": player_id,
            "stats": await self.server.redis.get_player_stats(player_id),
            "room_id": room_id,
            "room": self.server.content_loader.get_room(room_id),
        }
        module = pick_module(MODULES, ctx, self.rng)
        if module is None:
            # Silence still counts as Maestro's move; brief personal cooldown.
            self._next_ok[player_id] = now + 30.0
            return
        fired = await module["fire"](self.server, session, ctx)
        if fired:
            logger.info("Maestro fired %s on %s in %s", module["name"], player_id, room_id)
            self._set_cooldown(player_id, now)
            await self.server.push_character_snapshot(session)
