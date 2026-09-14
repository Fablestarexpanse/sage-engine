"""Maestro plugin: module interests, roulette selection, and firing through the host."""

import asyncio
import random

import pytest
from sage_plugin_maestro.main import Director, pick_module
from sage_plugin_maestro.modules import (
    MODULES,
    ambush_fire,
    ambush_interest,
    dread_fire,
    dread_interest,
    mercy_fire,
    mercy_interest,
)

from sage.world.models import EntityTemplate, ItemTemplate, RoomModel
from tests.fakes import StubSession, make_fake_server, repo_world


def _room(spawns: bool) -> RoomModel:
    return RoomModel(
        id="z:r", zone="z", type="chamber", entity_spawns=[{"template": "rat"}] if spawns else []
    )


def _ctx(hp=100, max_hp=100, spawns=True):
    return {
        "player_id": "p",
        "stats": {"hp": hp, "max_hp": max_hp},
        "room_id": "z:r",
        "room": _room(spawns),
    }


def test_ambush_needs_spawns_and_health():
    assert ambush_interest(_ctx(hp=100, spawns=True)) > 0
    assert ambush_interest(_ctx(hp=100, spawns=False)) == 0
    assert ambush_interest(_ctx(hp=30, spawns=True)) == 0
    assert ambush_interest({"stats": {"hp": 100}, "room": None}) == 0


def test_mercy_prefers_the_battered_and_dread_always_hums():
    assert mercy_interest(_ctx(hp=20)) > mercy_interest(_ctx(hp=100))
    assert dread_interest(_ctx()) > 0


def test_pick_module_mostly_nothing():
    rng = random.Random(7)
    picks = [pick_module(MODULES, _ctx(), rng) for _ in range(300)]
    assert sum(1 for p in picks if p is None) > 150


def test_pick_module_never_selects_zero_interest_and_survives_broken_modules():
    rng = random.Random(3)
    for _ in range(200):
        mod = pick_module(MODULES, _ctx(hp=100, spawns=False), rng)
        assert mod is None or mod["name"] != "ambush"
    assert all(pick_module(MODULES, _ctx(), rng, nothing_weight=0) for _ in range(50))
    broken = [{"name": "boom", "interest": lambda ctx: 1 / 0, "fire": None}]
    assert pick_module(broken, _ctx(), rng, nothing_weight=0) is None


@pytest.fixture
def director(plugin_host):
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    manifest.params["maestro.mercy_item"] = "bun"
    host = plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies), ["maestro"]
    )
    server = make_fake_server()
    server.redis = host.redis
    server.content_loader.entity_templates = {
        "gull": EntityTemplate(id="gull", name="grey gull", tags={"neutral"}),
        "rat": EntityTemplate(id="rat", name="river rat", tags={"hostile"}),
    }
    server.content_loader.item_templates = {"bun": ItemTemplate(id="bun", name="sweet bun")}
    host.server = server
    host.content = server.content_loader
    api = next(r.api for r in host.loaded if r.id == "maestro")
    return Director(api, rng=random.Random(1))


def test_ambush_spawns_only_hostiles_and_respects_the_room_cap(director):
    room = RoomModel(
        id="z:r",
        zone="z",
        type="chamber",
        entity_spawns=[{"template": "gull", "max_count": 5}, {"template": "rat", "max_count": 1}],
    )
    ctx = {"room": room, "room_id": "z:r", "stats": {"hp": 100, "max_hp": 100}}
    session = StubSession()
    assert asyncio.run(ambush_fire(director, session, ctx)) is True
    assert asyncio.run(ambush_fire(director, session, ctx)) is False
    assert len(asyncio.run(director.api._host.redis.get_room_entities("z:r"))) == 1
    assert "river rat lunges into the open" in session.sent[0]


def test_mercy_leaves_the_world_item_and_dread_uses_lexicon_lines(director):
    session = StubSession()
    ctx = {"room_id": "z:r", "stats": {"hp": 1, "max_hp": 100}}
    assert asyncio.run(mercy_fire(director, session, ctx)) is True
    assert "sweet bun" in session.sent[0]
    assert len(asyncio.run(director.api._host.redis.get_room_items("z:r"))) == 1

    assert asyncio.run(dread_fire(director, session, ctx)) is True
    assert session.sent[-1] in {
        director.api.t(k) for k in director.api.lexicon_keys("maestro.dread.")
    }
