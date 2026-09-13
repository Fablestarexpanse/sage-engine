"""Equipment: equip/unequip/swap, bonuses, display lines."""

from fablestar.items.equipment import (
    EQUIPMENT_KEY,
    equip_item,
    equipment_bonuses,
    equipped_lines,
    unequip_slot,
)
from fablestar.world.models import ItemTemplate

BLADE = ItemTemplate(id="scrap_blade", name="scrap-forged blade", slot="weapon", attack=2)
VEST = ItemTemplate(id="padded_vest", name="padded work vest", slot="armor", defense=1)
ROCK = ItemTemplate(id="rock", name="rock")

TEMPLATES = {t.id: t for t in (BLADE, VEST, ROCK)}


def _item(template: ItemTemplate, n: int = 1) -> dict:
    return {"id": f"{template.id}_{n}", "template": template.id, "name": template.name}


def test_equip_moves_item_out_of_inventory():
    stats: dict = {}
    blade = _item(BLADE)
    msg, inv = equip_item(stats, [blade], blade, BLADE)
    assert "equip the scrap-forged blade" in msg
    assert inv == []
    assert stats[EQUIPMENT_KEY]["weapon"]["id"] == blade["id"]


def test_equip_swap_returns_previous_to_inventory():
    stats: dict = {}
    old = _item(BLADE, 1)
    new = _item(BLADE, 2)
    _, inv = equip_item(stats, [old, new], old, BLADE)
    msg, inv = equip_item(stats, inv, new, BLADE)
    assert "stowing" in msg
    assert [it["id"] for it in inv] == [old["id"]]
    assert stats[EQUIPMENT_KEY]["weapon"]["id"] == new["id"]


def test_equip_rejects_slotless_item():
    stats: dict = {}
    rock = _item(ROCK)
    msg, inv = equip_item(stats, [rock], rock, ROCK)
    assert "can't be equipped" in msg
    assert inv == [rock]
    assert stats.get(EQUIPMENT_KEY) in (None, {})


def test_bonuses_sum_over_slots():
    stats: dict = {}
    equip_item(stats, [_item(BLADE)], _item(BLADE), BLADE)
    equip_item(stats, [_item(VEST)], _item(VEST), VEST)
    attack, defense = equipment_bonuses(stats, TEMPLATES.get)
    assert (attack, defense) == (2, 1)


def test_bonuses_empty_without_gear():
    assert equipment_bonuses({}, TEMPLATES.get) == (0, 0)


def test_unequip_by_slot_and_by_name():
    stats: dict = {}
    equip_item(stats, [_item(BLADE)], _item(BLADE), BLADE)
    msg, inv = unequip_slot(stats, [], "weapon")
    assert "unequip the scrap-forged blade" in msg
    assert len(inv) == 1 and stats[EQUIPMENT_KEY] == {}

    equip_item(stats, inv, inv[0], BLADE)
    msg, inv2 = unequip_slot(stats, [], "blade")
    assert inv2 is not None and stats[EQUIPMENT_KEY] == {}


def test_unequip_nothing_matched():
    msg, inv = unequip_slot({}, [], "hat")
    assert inv is None and "nothing like that" in msg


def test_equipped_lines_show_both_slots():
    stats: dict = {}
    equip_item(stats, [_item(BLADE)], _item(BLADE), BLADE)
    lines = equipped_lines(stats)
    assert lines[0] == "  weapon: scrap-forged blade"
    assert lines[1] == "  armor: —"
