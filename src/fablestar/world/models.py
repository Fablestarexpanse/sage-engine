"""Pydantic world models — RoomModel, EntityTemplate, ItemTemplate, StarSystemModel, ShipTemplate."""

from pydantic import BaseModel, Field, field_validator


class ExitModel(BaseModel):
    destination: str
    description: str
    one_way: bool = False


class SearchModel(BaseModel):
    """Scavenge profile on a feature — what searching it can yield."""

    items: list[str] = Field(min_length=1)  # item template ids
    max_finds: int = Field(default=1, ge=1)  # per respawn window (shared by all players)
    respawn_s: float = Field(default=600.0, gt=0)
    chance: float = Field(default=0.7, ge=0.0, le=1.0)  # base find chance per attempt


class FeatureModel(BaseModel):
    id: str
    name: str
    keywords: list[str]
    description: str
    interaction: str | None = "examine"
    search: SearchModel | None = None


class EntitySpawnModel(BaseModel):
    template: str
    chance: float = 1.0
    max_count: int = 1


class HazardModel(BaseModel):
    id: str
    type: str
    severity: int
    description: str


class AmbientModel(BaseModel):
    """Occasional atmosphere lines shown to players in the room (Epitaph 'room chats')."""

    lines: list[str] = Field(min_length=1)
    min_interval: float = Field(default=45.0, gt=0)
    max_interval: float = Field(default=120.0, gt=0)


class ShopStockModel(BaseModel):
    template: str
    price: int = Field(gt=0)


class ShopModel(BaseModel):
    """A room that trades: fixed sell stock, and optionally buys items for a
    fraction of their template value."""

    name: str = "the shop"
    sells: list[ShopStockModel] = Field(default_factory=list)
    buys: bool = False
    buy_rate: float = Field(default=0.5, gt=0, le=1.0)
    # Agent persona id of the shopkeeper, when an agent runs this shop.
    owner: str = ""


class RoomModel(BaseModel):
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
    hazards: list[HazardModel] = Field(default_factory=list)
    ambient: AmbientModel | None = None
    shop: ShopModel | None = None
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
    id: str
    name: str
    type: str = "misc"
    description: str = ""
    value: int = 0
    weight: float = 0.0
    heal: int = 0  # hp restored when consumed via `use` (0 = not consumable)
    slot: str | None = None  # equipment slot: "weapon" | "armor" (None = not equippable)
    attack: int = 0  # attack bonus while equipped
    defense: int = 0  # defense bonus while equipped
    # Ammo-fed weapon: item template consumed one per attack; without a round
    # in inventory the weapon's attack bonus does not apply (dry fire).
    ammo: str | None = None
    # Crafting: inputs (template id -> count) consumed to craft this item.
    # Empty dict = not craftable.
    recipe: dict[str, int] = Field(default_factory=dict)
    # How many of this item one craft produces (ammo batches etc.).
    yields: int = 1
    # Deconstruction outputs (template id -> count). Empty + no recipe = not
    # deconstructable; empty WITH a recipe = half the recipe rounded down
    # (minimum one of something).
    scraps: dict[str, int] = Field(default_factory=dict)
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


class StarSystemModel(BaseModel):
    """On-disk star system YAML under content/world/systems/."""

    id: str
    name: str
    coordinates: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    star: dict[str, str] = Field(default_factory=dict)
    faction: str = "neutral"
    security: str = "low"
    connections: list[SystemConnection] = Field(default_factory=list)
    bodies: list[CelestialBody] = Field(default_factory=list)


class ShipRoom(BaseModel):
    id: str
    name: str
    type: str = "room"
    description: dict[str, str] = Field(default_factory=dict)
    exits: dict[str, ExitModel] = Field(default_factory=dict)


class ShipTemplate(BaseModel):
    """Ship interior graph source (content/world/ships/)."""

    id: str
    name: str
    size: str = "small"
    rooms: list[ShipRoom] = Field(default_factory=list)


class GlyphEffectModel(BaseModel):
    type: str = "damage"
    magnitude: int = 0
    duration: int = 0
    cooldown: int = 0


class GlyphCostModel(BaseModel):
    energy: int = 0


class GlyphModel(BaseModel):
    """On-disk glyph ability YAML under content/world/glyphs/."""

    id: str
    name: str
    category: str = "combat"
    tier: int = 1
    body_slot: str = "forearm"
    description: str = ""
    inscription: str = ""
    effect: GlyphEffectModel = Field(default_factory=GlyphEffectModel)
    cost: GlyphCostModel = Field(default_factory=GlyphCostModel)
    prerequisites: list[str] = Field(default_factory=list)
    tags: set[str] = Field(default_factory=set)
