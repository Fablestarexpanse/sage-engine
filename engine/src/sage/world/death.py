"""Engine default death resolvers: when a character is dead, and how it comes back.

Worlds tune the default with params and replace it entirely by providing the
``death.check`` / ``death.respawn`` resolver slots from a plugin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# World params (world.toml [params]) read by the default respawn policy.
PARAM_RESPAWN_HP_FRACTION = "engine.death.respawn_hp_fraction"
PARAM_RESPAWN_BILL_MAX = "engine.death.respawn_bill_max"


@dataclass
class Respawn:
    room_id: str
    hp: int
    bill: int = 0


def default_death_check(stats: dict[str, Any]) -> bool:
    return int(stats.get("hp", 1)) <= 0


def default_respawn(world: Any, stats: dict[str, Any], wallet: int) -> Respawn:
    """Respawn room from the world manifest, a fraction of max hp, and an optional bill."""
    fraction = float(world.param(PARAM_RESPAWN_HP_FRACTION, 0.5))
    bill_max = int(world.param(PARAM_RESPAWN_BILL_MAX, 0))
    max_hp = int(stats.get("max_hp", 20))
    return Respawn(
        room_id=world.respawn_room,
        hp=max(1, int(max_hp * fraction)),
        bill=max(0, min(int(wallet), bill_max)),
    )
