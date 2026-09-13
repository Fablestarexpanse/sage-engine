"""Pydantic models for achievement definitions loaded from content/achievements/*.yaml."""

from pydantic import BaseModel, Field, field_validator

# Ordered smallest to largest; index is the tier rank shown to players.
ACHIEVEMENT_LEVELS = [
    "minor",
    "small",
    "moderate",
    "large",
    "huge",
    "massive",
    "epic",
    "legendary",
    "mythic",
]


class AchievementModel(BaseModel):
    """
    One achievement definition.

    criteria maps counter name -> threshold; the achievement is granted when
    every counter meets its threshold (match="all") or any one does
    (match="any"). Counters live inside the player stats blob under
    "counters" and are adjusted via achievements.engine.
    """

    id: str
    name: str
    story: str  # rendered as "<name>, in which you <story>"
    level: str = "minor"
    criteria: dict[str, int] = Field(min_length=1)
    match: str = "all"
    category: list[str] = Field(default_factory=list)
    instructions: str = ""

    @field_validator("level")
    @classmethod
    def _level_known(cls, v: str) -> str:
        if v not in ACHIEVEMENT_LEVELS:
            raise ValueError(f"level must be one of {ACHIEVEMENT_LEVELS}, got {v!r}")
        return v

    @field_validator("match")
    @classmethod
    def _match_known(cls, v: str) -> str:
        if v not in ("all", "any"):
            raise ValueError(f"match must be 'all' or 'any', got {v!r}")
        return v

    @property
    def level_rank(self) -> int:
        return ACHIEVEMENT_LEVELS.index(self.level)

    def story_line(self) -> str:
        return f"{self.name}, in which you {self.story}"
