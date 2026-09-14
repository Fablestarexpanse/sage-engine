"""Equipment: pure equip/unequip/bonus rules, and the commands and service through the host."""

from __future__ import annotations

import asyncio

from sage_plugin_equipment.rules import (
    EQUIPMENT_KEY,
    equip_item,
    equipment_bonuses,
    unequip_slot,
)

from tests.fakes import StubSession, repo_world

SLOTS = ["weapon", "armor"]
BONUSES = {"blade": (2, 0), "vest": (0, 1), "rock": (0, 0)}


def _item(template: str, n: int = 1) -> dict:
    return {"id": f"{template}_{n}", "template": template, "name": f"old {template}"}


def test_equip_moves_item_out_of_inventory():
    stats: dict = {}
    blade = _item("blade")
    slot, inv, previous = equip_item(stats, [blade], blade, "weapon", SLOTS)
    assert (slot, inv, previous) == ("weapon", [], None)
    assert stats[EQUIPMENT_KEY]["weapon"]["id"] == blade["id"]


def test_equip_swap_returns_previous_to_inventory():
    stats: dict = {}
    old, new = _item("blade", 1), _item("blade", 2)
    _, inv, _ = equip_item(stats, [old, new], old, "weapon", SLOTS)
    _, inv, previous = equip_item(stats, inv, new, "weapon", SLOTS)
    assert previous["id"] == old["id"]
    assert [it["id"] for it in inv] == [old["id"]]
    assert stats[EQUIPMENT_KEY]["weapon"]["id"] == new["id"]


def test_equip_refuses_items_without_a_world_slot():
    stats: dict = {}
    rock = _item("rock")
    assert equip_item(stats, [rock], rock, None, SLOTS) == (None, [rock], None)
    assert equip_item(stats, [rock], rock, "hat", SLOTS) == (None, [rock], None)
    assert stats.get(EQUIPMENT_KEY) in (None, {})


def test_bonuses_sum_over_slots():
    stats: dict = {}
    equip_item(stats, [], _item("blade"), "weapon", SLOTS)
    equip_item(stats, [], _item("vest"), "armor", SLOTS)
    assert equipment_bonuses(stats, BONUSES.get) == (2, 1)
    assert equipment_bonuses({}, BONUSES.get) == (0, 0)


def test_unequip_by_slot_and_by_name():
    stats: dict = {}
    equip_item(stats, [], _item("blade"), "weapon", SLOTS)
    item, inv = unequip_slot(stats, [], "weapon", SLOTS)
    assert item["template"] == "blade" and len(inv) == 1 and stats[EQUIPMENT_KEY] == {}

    equip_item(stats, inv, inv[0], "weapon", SLOTS)
    item, inv2 = unequip_slot(stats, [], "blade", SLOTS)
    assert item is not None and inv2 is not None and stats[EQUIPMENT_KEY] == {}
    assert unequip_slot({}, [], "hat", SLOTS) == (None, None)


ITEMS = {
    "club": "id: club\nname: iron club\nslot: weapon\nattack: 4\n",
    "coat": "id: coat\nname: oilskin coat\nslot: armor\ndefense: 2\n",
    "apple": "id: apple\nname: apple\n",
}


def _host(plugin_host, tmp_path):
    items = tmp_path / "content" / "world" / "items"
    items.mkdir(parents=True)
    for slug, body in ITEMS.items():
        (items / f"{slug}.yaml").write_text(body, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    manifest.transition.content_dir = str(tmp_path / "content")
    host = plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies), ["equipment"]
    )
    host.redis.stats["hero"] = {"hp": 10}
    host.redis.inventories["hero"] = [
        {"id": f"{t}_1", "template": t, "name": body.split("name: ")[1].split("\n")[0]}
        for t, body in ITEMS.items()
    ]
    return host


def _run(host, verb, session, *args):
    asyncio.run(host.registry.get(verb).handler(session, list(args)))


def test_commands_wear_show_and_remove_gear(plugin_host, tmp_path):
    host = _host(plugin_host, tmp_path)
    session = StubSession("hero")

    _run(host, "equip", session, "club")
    assert session.sent[-1] == "You equip the iron club as your weapon."
    _run(host, "equip", session, "apple")
    assert "can't be equipped" in session.sent[-1]
    _run(host, "equip", session, "coat")
    assert [it["template"] for it in host.redis.inventories["hero"]] == ["apple"]

    service = host.services["equipment"][1]
    assert service.bonuses(host.redis.stats["hero"]) == (4, 2)

    _run(host, "gear", session)
    assert "weapon: iron club" in session.sent[-1] and "armor: oilskin coat" in session.sent[-1]

    _run(host, "unequip", session, "weapon")
    assert session.sent[-1] == "You unequip the iron club."
    assert "club" not in [it["template"] for it in host.redis.stats["hero"]["equipment"].values()]
    _run(host, "unequip", session, "hat")
    assert "nothing like that" in session.sent[-1]
