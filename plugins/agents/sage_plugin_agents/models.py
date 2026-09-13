"""Agent persona models loaded from the world's content/agents/*.yaml — editable, hot-reloadable."""

from pydantic import BaseModel, Field


class TemperamentModel(BaseModel):
    warmth: float = 0.5
    caution: float = 0.5
    ambition: float = 0.5
    humor: float = 0.5


class MoodModel(BaseModel):
    valence: float = 0.0  # -1 (miserable) .. 1 (joyful)
    arousal: float = 0.3  # 0 (flat) .. 1 (agitated)


class AgentPersonaModel(BaseModel):
    """One agent's editable sheet. `name` doubles as its player_id in the world."""

    id: str
    name: str
    spawn_room: str
    enabled: bool = True
    temperament: TemperamentModel = Field(default_factory=TemperamentModel)
    wants: str = ""
    fears: str = ""
    speech: str = ""
    baseline_mood: MoodModel = Field(default_factory=MoodModel)
    # Non-negotiable facts the validator/prompts always assert (list of "k: v" strings).
    hard_facts: list[str] = Field(default_factory=list)
    # Room slugs (same zone as spawn_room) the Body wanders between when idle.
    routine: list[str] = Field(default_factory=list)
    # slot -> item template id, equipped on spawn.
    gear: dict[str, str] = Field(default_factory=dict)
    stats: dict[str, int] = Field(default_factory=lambda: {"hp": 60, "max_hp": 60})
    # Attribute spread, seeded through the world's progression (the same block a new player
    # gets); keys the world doesn't define are ignored.
    attributes: dict[str, int] = Field(default_factory=dict)
    # Starting balance in the world's primary currency.
    money: int = 25

    def spawn_zone(self) -> str:
        return self.spawn_room.split(":")[0] if ":" in self.spawn_room else ""
