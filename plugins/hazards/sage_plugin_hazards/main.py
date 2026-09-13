"""Hazards plugin: a room's hazards roll against whoever walks in."""

from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel, RootModel

from sage.api import PluginAPI, RoomEntered

RESIST_CAP = 0.75


class HazardModel(BaseModel):
    id: str
    type: str
    severity: int
    description: str


class Hazards(RootModel[list[HazardModel]]):
    """`hazards:` — the room's list of hazards."""


def apply_hazards(
    api: PluginAPI,
    stats: dict[str, Any],
    hazards: list[HazardModel],
    resist: float,
    rng: random.Random,
    now: float | None = None,
) -> list[str]:
    """Roll each hazard; failed resists apply a DoT (severity drives damage and duration)."""
    messages: list[str] = []
    for hazard in hazards:
        if rng.random() < resist:
            messages.append(api.t("hazards.resisted", type=hazard.type))
            continue
        severity = max(1, int(hazard.severity))
        effect = api.effects.make(
            f"hazard.{hazard.type}",
            name=hazard.type,
            description=hazard.description,
            kind="dot",
            magnitude=severity,
            interval=6.0,
            duration=6.0 * (2 + severity),  # severity 1 -> 18 s, 3 ticks
            now=now,
        )
        api.effects.apply(stats, effect)
        messages.append(
            api.t("hazards.takes_hold", description=hazard.description, type=hazard.type)
        )
    return messages


def setup(api: PluginAPI) -> None:
    api.content.extend("room", "hazards", Hazards)
    rng = random.Random()
    # The world's resist skill (a progression skill id): each level adds per_level resist chance.
    skill = api.param("resist_skill", None)
    per_level = float(api.param("resist_per_level", 0.01))

    async def on_enter(event: RoomEntered) -> None:
        room = api.content.room(event.room_id)
        claimed = api.content.extension(room, "room", "hazards") if room else None
        if not claimed or not claimed.root:
            return
        async with api.state.edit(event.player_id) as stats:
            resist = min(RESIST_CAP, api.progression.skill_level(stats, skill) * per_level)
            event.messages.extend(apply_hazards(api, stats, claimed.root, resist, rng))
        await api.progression.skill_used(event.player_id, skill, chance=0.15)

    api.events.subscribe(RoomEntered, on_enter)
