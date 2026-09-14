"""The `search:` block on a room feature, and find-chance math."""

from pydantic import BaseModel, Field

CHANCE_CAP = 0.95


class SearchModel(BaseModel):
    """Scavenge profile on a feature — what searching it can yield."""

    items: list[str] = Field(min_length=1)  # item template ids
    max_finds: int = Field(default=1, ge=1)  # per respawn window (shared by all players)
    respawn_s: float = Field(default=600.0, gt=0)
    chance: float = Field(default=0.7, ge=0.0, le=1.0)  # base find chance per attempt


def find_chance(base: float, skill_level: int, per_level: float) -> float:
    """Base chance plus per_level for every level of the world's search skill, capped."""
    return min(CHANCE_CAP, base + max(0, skill_level) * per_level)


def finds_key(room_id: str, feature_id: str) -> str:
    return f"search:{room_id}:{feature_id}:finds"
