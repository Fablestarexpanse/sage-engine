"""Search plugin: profile validation, chance math, content integrity, and a find through the host."""

import asyncio

import pytest
from pydantic import ValidationError
from sage_plugin_search.rules import CHANCE_CAP, SearchModel, find_chance

from sage.world.progression import SKILL_LEVEL, SKILL_USED
from tests.fakes import StubSession, repo_world


def test_search_model_defaults_and_requires_items():
    s = SearchModel(items=["lamp"])
    assert (s.max_finds, s.respawn_s, s.chance) == (1, 600.0, 0.7)
    with pytest.raises(ValidationError):
        SearchModel(items=[])


def test_find_chance_scales_with_skill_and_caps():
    assert find_chance(0.6, 0, 0.005) == 0.6
    assert find_chance(0.6, 20, 0.005) == pytest.approx(0.7)
    assert find_chance(0.6, 1000, 0.005) == CHANCE_CAP
    assert find_chance(0.5, -50, 0.005) == 0.5


def test_every_search_profile_in_the_world_references_real_items(plugin_host):
    host = plugin_host(repo_world(), ["search"])
    service = host.services["search"][1]
    searchable = 0
    for room_id in host.content.list_room_ids():
        room = host.content.get_room(room_id)
        for feature in room.features if room else []:
            profile = service.profile(feature)
            if profile is None:
                continue
            searchable += 1
            for item_id in profile.items:
                assert host.content.get_item_template(item_id), f"{room_id}: unknown {item_id}"
    assert searchable, "the world should ship at least one searchable feature"


ROOM = """id: town:cellar
zone: town
type: hub
features:
  - id: crates
    name: old crates
    keywords: [crates]
    description: Dusty.
    search: {items: [lamp], max_finds: 1, chance: 1.0}
"""


def test_a_find_fills_the_pack_counts_and_reports_skill_use(plugin_host, tmp_path, monkeypatch):
    # Find chance caps below 1.0, so pin the roll: this test is about what a find does.
    monkeypatch.setattr("random.random", lambda: 0.0)
    rooms = tmp_path / "content" / "world" / "zones" / "town" / "rooms"
    items = tmp_path / "content" / "world" / "items"
    rooms.mkdir(parents=True)
    items.mkdir(parents=True)
    (rooms / "cellar.yaml").write_text(ROOM, encoding="utf-8")
    (items / "lamp.yaml").write_text("id: lamp\nname: brass lamp\nvalue: 3\n", encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    manifest.transition.content_dir = str(tmp_path / "content")
    manifest.params["search.skill"] = "looking"
    world = type(world)(world.root, manifest, world.stats, world.currencies)

    host = plugin_host(world, ["search"])
    used: list[tuple] = []

    async def skill_used(player_id, skill, chance):
        used.append((player_id, skill, chance))

    host.resolvers.define(SKILL_USED, skill_used)
    host.resolvers.define(SKILL_LEVEL, lambda stats, skill: 0)
    host.redis.locations["hero"] = "town:cellar"
    host.redis.stats["hero"] = {"hp": 3}

    session = StubSession("hero")
    handler = host.registry.get("search").handler
    asyncio.run(handler(session, ["crates"]))
    assert session.sent[0] == "Tucked away in the old crates, you find: brass lamp."
    assert [it["template"] for it in host.redis.inventories["hero"]] == ["lamp"]
    assert host.redis.stats["hero"]["counters"]["scavenged"] == 1
    assert used == [("hero", "looking", 0.2)]

    asyncio.run(handler(session, []))
    assert session.sent[-1] == "The old crates has been picked clean. Maybe later."
