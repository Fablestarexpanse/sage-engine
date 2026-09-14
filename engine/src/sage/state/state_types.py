"""TypedDict schemas for JSON-shaped state (character stats, inventory, entity/item state).

These document the shapes stored in Redis and in the Postgres JSON columns
(Character.stats, Character.inventory). They are structural annotations only —
neither store enforces them at runtime.

World and plugin blocks inside the stats blob are documented by their owners.
"""

from typing import Any, TypedDict


class CharacterStats(TypedDict, total=False):
    """Shape of Character.stats / player:stats:{id}. total=False: legacy rows may omit keys."""

    strength: int
    dexterity: int
    intelligence: int
    perception: int
    hp: int
    max_hp: int


class InventoryItem(TypedDict, total=False):
    """One entry in Character.inventory / player:inv:{id}."""

    id: str
    template: str
    name: str
    description: str
    value: int


class EntityState(TypedDict, total=False):
    """Live entity state at entity:state:{id}."""

    id: str
    name: str
    template: str
    room_id: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    alive: bool
    loot: list[str]


class ItemState(TypedDict, total=False):
    """Live floor-item state at item:state:{id}."""

    id: str
    name: str
    template: str
    room_id: str
    description: str
    value: int
    weight: float


# Play API responses are open dicts with a guaranteed "ok" discriminator.
PlayResponse = dict[str, Any]
