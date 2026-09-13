"""Maestro director: every check window it considers each connected player; if their personal
cooldown has lapsed, it roulette-selects among applicable modules, with a heavy "nothing happens"
weight, because dread needs silence between notes."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from sage.api import PluginAPI

from .modules import MODULES

logger = logging.getLogger(__name__)

COOLDOWN_RANGE_S = (90.0, 240.0)  # min silence per player after any firing
SILENCE_COOLDOWN_S = 30.0  # choosing nothing still counts as a move
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


class Director:
    def __init__(self, api: PluginAPI, rng: random.Random | None = None):
        self.api = api
        self.rng = rng or random.Random()
        self.mercy_item: str | None = api.param("mercy_item", None)
        self.hostile_tag: str = api.param("hostile_tag", "hostile")
        self.nothing_weight = int(api.param("nothing_weight", NOTHING_WEIGHT))
        self._next_ok: dict[str, float] = {}  # player_id -> monotonic time

    async def on_check(self, tick: int) -> None:
        now = time.monotonic()
        online = self.api.sessions.online()
        for player_id in online:
            try:
                await self.consider(player_id, now)
            except Exception as exc:
                logger.warning("Maestro consider failed for %s: %s", player_id, exc)
        for player_id in [p for p in self._next_ok if p not in set(online)]:
            del self._next_ok[player_id]

    async def consider(self, player_id: str, now: float) -> None:
        if now < self._next_ok.get(player_id, 0.0):
            return
        session = self.api.sessions.get(player_id)
        room_id = await self.api.state.location(player_id)
        if session is None or not room_id:
            return
        ctx = {
            "player_id": player_id,
            "stats": await self.api.state.snapshot(player_id),
            "room_id": room_id,
            "room": self.api.content.room(room_id),
        }
        module = pick_module(MODULES, ctx, self.rng, self.nothing_weight)
        if module is None:
            self._next_ok[player_id] = now + SILENCE_COOLDOWN_S
            return
        if await module["fire"](self, session, ctx):
            logger.info("Maestro fired %s on %s in %s", module["name"], player_id, room_id)
            self._next_ok[player_id] = now + self.rng.uniform(*COOLDOWN_RANGE_S)
            await self.api.sessions.push_snapshot(session)


def setup(api: PluginAPI) -> None:
    director = Director(api)
    api.tick.every(float(api.param("check_seconds", 30)), director.on_check, name="director")
