"""Progression resolver slots (contracts catalog #3): how using a skill advances a character.

Plugins report activity by skill id — a string the world chooses (a dotted proficiency leaf in
one world, plain ``smithing`` in another). The world's progression provider decides what that means. With no provider, skill use does nothing
and every skill reads as level 0, so a world without progression still plays.
"""

from __future__ import annotations

from typing import Any

SKILL_USED = "progression.skill_used"
SKILL_LEVEL = "progression.skill_level"


async def default_skill_used(player_id: str, skill: str, chance: float) -> None:
    """(player_id, skill, chance): a chance-gated advancement attempt. Default: nothing."""
    return None


def default_skill_level(stats: dict[str, Any], skill: str) -> int:
    """(stats, skill) -> level. Default: 0."""
    return 0
