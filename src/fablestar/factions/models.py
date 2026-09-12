"""Faction definitions loaded from content/factions/*.yaml."""

from pydantic import BaseModel, Field

# Ordered worst → best; thresholds map a numeric rep onto these names.
STANDING_LEVELS = [
    ("loathed", -100),
    ("hated", -60),
    ("disliked", -20),
    ("neutral", 20),
    ("liked", 60),
    ("loved", 100),
    ("exalted", 10**9),
]

REP_MIN = -200
REP_MAX = 200


def standing_name(rep: int) -> str:
    """Map a numeric reputation onto its standing label."""
    for name, upper in STANDING_LEVELS:
        if rep < upper:
            return name
    return STANDING_LEVELS[-1][0]


class FactionModel(BaseModel):
    id: str
    name: str
    description: str = ""
    initial_rep: int = 0
    # Rep change when the player kills an entity whose template's `faction`
    # names this faction. Negative for allies/members, positive for factions
    # that consider the target vermin.
    kill_rep: int = -10
    # Entity template ids this faction treats as enemies: killing one of these
    # RAISES standing with this faction by `enemy_kill_rep`.
    enemies: list[str] = Field(default_factory=list)
    enemy_kill_rep: int = 2
    tags: list[str] = Field(default_factory=list)
