"""
Equipment rules — pure functions over the stats blob and inventory list.

Worn items live at stats["equipment"] = {slot: inventory-item-dict}, moved out of the inventory
while worn, so persistence and the character snapshot carry them for free. Slots are the
world's (world.toml [content] equipment_slots).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

EQUIPMENT_KEY = "equipment"


def ensure_equipment(stats: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(stats.get(EQUIPMENT_KEY), dict):
        stats[EQUIPMENT_KEY] = {}
    return stats[EQUIPMENT_KEY]


def equipment_bonuses(
    stats: dict[str, Any], bonuses_of: Callable[[str], tuple[int, int]]
) -> tuple[int, int]:
    """(attack, defense) from worn gear; bonuses_of(template_id) -> (attack, defense)."""
    attack = defense = 0
    for item in ensure_equipment(stats).values():
        if item:
            a, d = bonuses_of(item.get("template", ""))
            attack += a
            defense += d
    return attack, defense


def equip_item(
    stats: dict[str, Any],
    inventory: list[dict[str, Any]],
    item: dict[str, Any],
    slot: str | None,
    slots: list[str],
) -> tuple[str | None, list[dict[str, Any]], dict[str, Any] | None]:
    """
    Wear one inventory item in `slot`. Returns (slot worn or None, new_inventory, previous item).
    Anything already in the slot goes back into the inventory.
    """
    if slot not in slots:
        return None, inventory, None
    equipment = ensure_equipment(stats)
    new_inventory = [it for it in inventory if it.get("id") != item.get("id")]
    previous = equipment.get(slot)
    if previous:
        new_inventory.append(previous)
    equipment[slot] = item
    return slot, new_inventory, previous


def unequip_slot(
    stats: dict[str, Any], inventory: list[dict[str, Any]], needle: str, slots: list[str]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    """Remove gear by slot name or item-name fragment. Returns (item, new_inventory) or (None, None)."""
    equipment = ensure_equipment(stats)
    needle = needle.lower().strip()
    for slot in slots:
        item = equipment.get(slot)
        if not item:
            continue
        if needle in (slot, "") or needle in item.get("name", "").lower():
            del equipment[slot]
            return item, [*inventory, item]
    return None, None
