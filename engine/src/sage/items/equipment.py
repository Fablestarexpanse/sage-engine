"""
Equipment — pure functions over the stats blob + inventory list.

Equipped items live at stats["equipment"] = {slot: inventory-item-dict}, moved
out of the inventory list while worn, so persistence and the character
snapshot carry them for free. Slots: "weapon", "armor".
"""

from typing import Any

from sage.world.models import ItemTemplate

EQUIPMENT_KEY = "equipment"
SLOTS = ("weapon", "armor")


def ensure_equipment(stats: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(stats.get(EQUIPMENT_KEY), dict):
        stats[EQUIPMENT_KEY] = {}
    return stats[EQUIPMENT_KEY]


def equipment_bonuses(stats: dict[str, Any], get_template) -> tuple[int, int]:
    """(attack, defense) from worn gear; get_template resolves template ids."""
    attack = defense = 0
    for item in ensure_equipment(stats).values():
        template = get_template(item.get("template", "")) if item else None
        if template is not None:
            attack += int(template.attack)
            defense += int(template.defense)
    return attack, defense


def equip_item(
    stats: dict[str, Any],
    inventory: list[dict[str, Any]],
    item: dict[str, Any],
    template: ItemTemplate,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Wear one inventory item. Returns (message, new_inventory); anything already
    in the slot goes back into the inventory.
    """
    if template.slot not in SLOTS:
        return (f"The {item.get('name', 'item')} can't be equipped.", inventory)
    equipment = ensure_equipment(stats)
    new_inventory = [it for it in inventory if it.get("id") != item.get("id")]
    previous = equipment.get(template.slot)
    if previous:
        new_inventory.append(previous)
    equipment[template.slot] = item
    swap = f" (stowing the {previous.get('name', 'old gear')})" if previous else ""
    return (
        f"You equip the {item.get('name', 'item')} as your {template.slot}{swap}.",
        new_inventory,
    )


def unequip_slot(
    stats: dict[str, Any],
    inventory: list[dict[str, Any]],
    needle: str,
) -> tuple[str, list[dict[str, Any]] | None]:
    """
    Remove gear by slot name or item-name fragment. Returns (message,
    new_inventory) — new_inventory None when nothing matched.
    """
    equipment = ensure_equipment(stats)
    needle = needle.lower().strip()
    for slot in SLOTS:
        item = equipment.get(slot)
        if not item:
            continue
        if needle in (slot, "") or needle in item.get("name", "").lower():
            del equipment[slot]
            return (f"You unequip the {item.get('name', 'item')}.", [*inventory, item])
    return ("You have nothing like that equipped.", None)


def equipped_lines(stats: dict[str, Any]) -> list[str]:
    equipment = ensure_equipment(stats)
    lines = []
    for slot in SLOTS:
        item = equipment.get(slot)
        lines.append(f"  {slot}: {item.get('name') if item else '—'}")
    return lines
