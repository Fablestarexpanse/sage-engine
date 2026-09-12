"""Generated faction missions: generation, kill progress, collect completion."""

import random

from fablestar.factions.engine import FACTIONS_KEY
from fablestar.factions.missions import (
    MISSION_KEY,
    active_mission,
    describe_mission,
    generate_mission,
    record_kill,
    try_complete_collect,
    will_deal,
)
from fablestar.factions.models import FactionModel
from fablestar.factions.registry import FactionRegistry


def _guild(**overrides) -> FactionModel:
    base = {
        "id": "guild",
        "name": "Guild",
        "description": "d",
        "enemies": ["scrap_drone"],
        "mission_rep": 12,
    }
    base.update(overrides)
    return FactionModel(**base)


def _union(**overrides) -> FactionModel:
    base = {
        "id": "union",
        "name": "Union",
        "description": "d",
        "wanted_items": ["power_cell"],
        "mission_rep": 10,
    }
    base.update(overrides)
    return FactionModel(**base)


def _inv_item(template: str, n: int) -> dict:
    return {"id": f"{template}_{n}", "template": template, "name": template}


def test_generate_kill_mission_from_enemies():
    m = generate_mission(_guild(), rng=random.Random(1))
    assert m["kind"] == "kill" and m["target"] == "scrap_drone"
    assert 3 <= m["count"] <= 5 and m["progress"] == 0


def test_generate_collect_mission_from_wanted_items():
    m = generate_mission(_union(), rng=random.Random(1))
    assert m["kind"] == "collect" and m["target"] == "power_cell"
    assert 2 <= m["count"] <= 3


def test_generate_none_when_faction_offers_nothing():
    f = FactionModel(id="x", name="X")
    assert not f.offers_missions()
    assert generate_mission(f, rng=random.Random(1)) is None


def test_will_deal_refuses_hated():
    f = _guild()
    stats = {FACTIONS_KEY: {"guild": -70}}
    assert not will_deal(stats, f)
    assert will_deal({}, f)


def test_record_kill_progresses_and_completes():
    guild = _guild()
    reg = FactionRegistry([guild])
    stats: dict = {
        MISSION_KEY: {
            "faction": "guild",
            "kind": "kill",
            "target": "scrap_drone",
            "count": 2,
            "progress": 0,
        }
    }
    msgs, done = record_kill(stats, reg, "scrap_drone")
    assert not done and "1/2" in msgs[0]
    msgs, done = record_kill(stats, reg, "scrap_drone")
    assert done
    assert active_mission(stats) is None
    assert stats[FACTIONS_KEY]["guild"] == 12
    assert any("Mission complete" in m for m in msgs)


def test_record_kill_ignores_wrong_template():
    reg = FactionRegistry([_guild()])
    stats: dict = {
        MISSION_KEY: {
            "faction": "guild",
            "kind": "kill",
            "target": "scrap_drone",
            "count": 2,
            "progress": 0,
        }
    }
    msgs, done = record_kill(stats, reg, "rat")
    assert msgs == [] and not done
    assert stats[MISSION_KEY]["progress"] == 0


def test_collect_completion_consumes_exactly_needed():
    union = _union()
    reg = FactionRegistry([union])
    stats: dict = {
        MISSION_KEY: {
            "faction": "union",
            "kind": "collect",
            "target": "power_cell",
            "count": 2,
            "progress": 0,
        }
    }
    inv = [
        _inv_item("power_cell", 1),
        _inv_item("power_cell", 2),
        _inv_item("power_cell", 3),
        _inv_item("ration_pack", 1),
    ]
    msgs, new_inv = try_complete_collect(stats, reg, inv)
    assert new_inv is not None
    assert len([i for i in new_inv if i["template"] == "power_cell"]) == 1
    assert len([i for i in new_inv if i["template"] == "ration_pack"]) == 1
    assert active_mission(stats) is None
    assert stats[FACTIONS_KEY]["union"] == 10
    assert any("Mission complete" in m for m in msgs)


def test_collect_insufficient_items_keeps_mission():
    reg = FactionRegistry([_union()])
    stats: dict = {
        MISSION_KEY: {
            "faction": "union",
            "kind": "collect",
            "target": "power_cell",
            "count": 3,
            "progress": 0,
        }
    }
    msgs, new_inv = try_complete_collect(stats, reg, [_inv_item("power_cell", 1)])
    assert new_inv is None
    assert active_mission(stats) is not None
    assert "carrying 1" in msgs[0]


def test_collect_without_mission():
    reg = FactionRegistry([])
    msgs, new_inv = try_complete_collect({}, reg, [])
    assert new_inv is None and "no delivery" in msgs[0]


def test_describe_mission_uses_faction_name():
    reg = FactionRegistry([_guild()])
    m = {"faction": "guild", "kind": "kill", "target": "scrap_drone", "count": 3, "progress": 1}
    assert describe_mission(m, reg) == "Destroy 3x scrap_drone for Guild (1/3)"
