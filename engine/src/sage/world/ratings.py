"""Combat ratings slot: how a character's stats become attack and defense numbers."""

from __future__ import annotations

from typing import Any

RATINGS = "combat.ratings"


DEFAULT_ATTACK = 3
DEFAULT_DEFENSE = 2


def default_ratings(stats: dict[str, Any]) -> tuple[int, int]:
    """(stats) -> (attack, defense) before gear. Default: flat numbers.

    Which attributes make a fighter is the world's call, so the engine reads none of them; a
    world's progression plugin provides this slot.
    """
    return DEFAULT_ATTACK, DEFAULT_DEFENSE
