"""Maestro: module interests and roulette selection."""

import random

from fablestar.maestro.director import pick_module
from fablestar.maestro.modules import MODULES, _ambush_interest, _dread_interest, _mercy_interest
from fablestar.world.models import RoomModel


def _room(spawns: bool) -> RoomModel:
    return RoomModel(
        id="z:r",
        zone="z",
        type="chamber",
        entity_spawns=[{"template": "scrap_drone"}] if spawns else [],
    )


def _ctx(hp=100, max_hp=100, spawns=True):
    return {
        "player_id": "p",
        "stats": {"hp": hp, "max_hp": max_hp},
        "room_id": "z:r",
        "room": _room(spawns),
    }


def test_ambush_needs_spawns_and_health():
    assert _ambush_interest(_ctx(hp=100, spawns=True)) > 0
    assert _ambush_interest(_ctx(hp=100, spawns=False)) == 0
    assert _ambush_interest(_ctx(hp=30, spawns=True)) == 0
    assert _ambush_interest({"stats": {"hp": 100}, "room": None}) == 0


def test_mercy_prefers_the_battered():
    assert _mercy_interest(_ctx(hp=20)) > _mercy_interest(_ctx(hp=100))


def test_dread_always_slightly_interested():
    assert _dread_interest(_ctx()) > 0


def test_pick_module_mostly_nothing():
    rng = random.Random(7)
    picks = [pick_module(MODULES, _ctx(), rng) for _ in range(300)]
    nothings = sum(1 for p in picks if p is None)
    # nothing_weight 60 vs ~12+2+5 applicable → silence should dominate
    assert nothings > 150


def test_pick_module_never_selects_zero_interest():
    rng = random.Random(3)
    ctx = _ctx(hp=100, spawns=False)  # ambush ineligible
    for _ in range(200):
        mod = pick_module(MODULES, ctx, rng)
        assert mod is None or mod["name"] != "ambush"


def test_pick_module_zero_nothing_weight_always_fires():
    rng = random.Random(5)
    for _ in range(50):
        mod = pick_module(MODULES, _ctx(), rng, nothing_weight=0)
        assert mod is not None


def test_pick_module_handles_broken_interest():
    rng = random.Random(1)
    broken = [{"name": "boom", "interest": lambda ctx: 1 / 0, "fire": None}]
    assert pick_module(broken, _ctx(), rng, nothing_weight=0) is None


def test_ambush_respects_cap_and_skips_neutral():
    import asyncio

    from fablestar.maestro.modules import _ambush_fire
    from fablestar.world.models import EntityTemplate
    from tests.fakes import StubSession, make_fake_server

    server = make_fake_server()
    server.content_loader.entity_templates = {
        "gullwing": EntityTemplate(id="gullwing", name="grey gullwing", tags={"neutral"}),
        "scrap_drone": EntityTemplate(id="scrap_drone", name="scrap drone", tags={"hostile"}),
    }
    room = RoomModel(
        id="z:r",
        zone="z",
        type="chamber",
        entity_spawns=[
            {"template": "gullwing", "max_count": 5},
            {"template": "scrap_drone", "max_count": 1},
        ],
    )
    ctx = {"room": room, "room_id": "z:r", "stats": {"hp": 100, "max_hp": 100}}

    async def run():
        first = await _ambush_fire(server, StubSession(), ctx)
        second = await _ambush_fire(server, StubSession(), ctx)
        return first, second, await server.redis.get_room_entities("z:r")

    first, second, ents = asyncio.run(run())
    assert first is True
    assert second is False
    assert len(ents) == 1
