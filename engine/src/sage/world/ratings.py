"""Combat ratings slot: how a character's stats become attack and defense numbers."""

from __future__ import annotations

from typing import Any

RATINGS = "combat.ratings"


def default_ratings(stats: dict[str, Any]) -> tuple[int, int]:
    """(stats) -> (attack, defense) from plain strength/dexterity (before gear)."""
    return (
        max(1, int(stats.get("strength", 10)) // 3),
        max(1, int(stats.get("dexterity", 10)) // 5),
    )
