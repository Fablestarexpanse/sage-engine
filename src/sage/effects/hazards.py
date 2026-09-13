"""Room hazards → effects. First real consumer of the effects engine."""

import random
from typing import Any

from sage.effects.engine import apply_effect, make_effect
from sage.proficiencies.state_helpers import CONDUIT_KEY
from sage.world.models import RoomModel

HAZARD_RESIST_LEAF = "traversal.survival.hazard_resist"
# Each level of hazard_resist adds 1% chance to shrug a hazard off, capped.
RESIST_CAP = 0.75


def _resist_chance(stats: dict[str, Any]) -> float:
    try:
        level = int(stats[CONDUIT_KEY]["proficiencies"][HAZARD_RESIST_LEAF]["level"])
    except (KeyError, TypeError, ValueError):
        level = 0
    return min(RESIST_CAP, level * 0.01)


def apply_room_hazards(
    stats: dict[str, Any],
    room: RoomModel,
    rng: random.Random | None = None,
    now: float | None = None,
) -> list[str]:
    """
    Roll each hazard in the room against the player. Mutates stats (effects
    applied on failure) and returns player-facing messages. Severity drives
    both damage per tick and duration.
    """
    if not room.hazards:
        return []
    rng = rng or random.Random()
    messages: list[str] = []
    resist = _resist_chance(stats)
    for hazard in room.hazards:
        if rng.random() < resist:
            messages.append(f"You brace against the {hazard.type} and shrug it off.")
            continue
        severity = max(1, int(hazard.severity))
        effect = make_effect(
            f"hazard.{hazard.type}",
            name=hazard.type,
            description=hazard.description,
            kind="dot",
            magnitude=severity,
            interval=6.0,
            duration=6.0 * (2 + severity),  # severity 1 → 18 s, 3 ticks
            now=now,
        )
        apply_effect(stats, effect)
        messages.append(f"{hazard.description} ({hazard.type} takes hold)")
    return messages
