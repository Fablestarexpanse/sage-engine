"""Pydantic world models — RoomModel, EntityTemplate, ItemTemplate."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExitModel(BaseModel):
    destination: str
    description: str
    one_way: bool = False


class FeatureModel(BaseModel):
    # Unknown fields are kept: plugins claim them as content extensions (sage.world.extensions).
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    keywords: list[str]
    description: str
    interaction: str | None = "examine"


class EntitySpawnModel(BaseModel):
    template: str
    chance: float = 1.0
    max_count: int = 1


class RoomModel(BaseModel):
    # Unknown fields are kept: plugins claim them as content extensions (sage.world.extensions).
    model_config = ConfigDict(extra="allow")

    id: str
    zone: str
    name: str | None = None  # display name (WorldForge writes it; falls back to the id)
    type: str
    depth: int = 1
    group: str | None = None
    description: dict[str, str] = Field(default_factory=lambda: {"base": "A featureless room."})
    exits: dict[str, ExitModel] = Field(default_factory=dict)
    features: list[FeatureModel] = Field(default_factory=list)
    entity_spawns: list[EntitySpawnModel] = Field(default_factory=list)
    tags: set[str] = Field(default_factory=set)


class ZoneModel(BaseModel):
    id: str
    name: str
    description: str
    depth_range: list[int] = Field(default_factory=lambda: [1, 3])


class LootEntryModel(BaseModel):
    """One drop-table row: template, drop chance, and how many drop."""

    template: str
    chance: float = Field(default=0.6, gt=0, le=1.0)
    count: int = Field(default=1, ge=1)


class EntityTemplate(BaseModel):
    # Unknown fields are kept: plugins claim them as content extensions (sage.world.extensions).
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    type: str = "creature"
    description: dict[str, str] = Field(
        default_factory=lambda: {"short": "A creature.", "long": "A creature lurks here."}
    )
    stats: dict[str, int] = Field(
        default_factory=lambda: {"hp": 10, "max_hp": 10, "attack": 3, "defense": 1}
    )
    tags: set[str] = Field(default_factory=set)
    # Drop table. YAML accepts bare template ids (legacy, 60% chance) or
    # {template, chance, count} rows; both normalize to LootEntryModel.
    loot: list[LootEntryModel] = Field(default_factory=list)
    faction: str | None = None  # faction id (content/factions/) that owns this entity

    @field_validator("loot", mode="before")
    @classmethod
    def _coerce_loot(cls, v):
        out = []
        for entry in v or []:
            if isinstance(entry, str):
                out.append({"template": entry})
            else:
                out.append(entry)
        return out


class ItemTemplate(BaseModel):
    # Unknown fields are kept: plugins claim them as content extensions (sage.world.extensions).
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    type: str = "misc"
    description: str = ""
    value: int = 0
    weight: float = 0.0
    tags: set[str] = Field(default_factory=set)


class SystemConnection(BaseModel):
    target: str
    type: str
    bidirectional: bool = True
    stability: str | None = None


class ZoneRef(BaseModel):
    zone_ref: str


class CelestialBody(BaseModel):
    id: str
    type: str
    name: str
    orbit: float | None = None
    orbits: str | None = None
    zones: list[ZoneRef] = Field(default_factory=list)
