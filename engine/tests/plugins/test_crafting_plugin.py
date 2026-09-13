"""Crafting plugin: recipe math, and crafting/deconstructing through the host."""

import asyncio

from sage_plugin_crafting.rules import missing_for, scrap_yield

from sage.world.progression import SKILL_LEVEL, SKILL_USED
from tests.fakes import StubSession, repo_world


def _inv(*templates):
    return [{"id": f"{t}_{i}", "template": t, "name": t} for i, t in enumerate(templates)]


def test_missing_for_reports_gaps():
    recipe = {"wick": 2, "tin": 1}
    assert missing_for(recipe, _inv("wick", "wick", "tin")) == {}
    assert missing_for(recipe, _inv("wick")) == {"wick": 1, "tin": 1}


def test_scrap_yield_rules():
    assert scrap_yield({"a": 4}, {"b": 2}) == {"b": 2}
    assert scrap_yield({"a": 4, "b": 1}, {}) == {"a": 2}
    assert scrap_yield({"a": 1}, {}) == {"a": 1}
    assert scrap_yield({}, {}) == {}


ITEMS = {
    "wick": "id: wick\nname: wick\nvalue: 1\n",
    "tin": "id: tin\nname: tin cup\nvalue: 1\n",
    "lamp": "id: lamp\nname: tin lamp\ntype: tool\nvalue: 5\nrecipe: {wick: 2, tin: 1}\nyields: 2\n",
    "sword": "id: sword\nname: sword\nslot: weapon\nvalue: 9\nrecipe: [not, a, mapping]\n",
}


def _workshop(plugin_host, tmp_path):
    items = tmp_path / "content" / "world" / "items"
    items.mkdir(parents=True)
    for tid, body in ITEMS.items():
        (items / f"{tid}.yaml").write_text(body, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    manifest.transition.content_dir = str(tmp_path / "content")
    manifest.params["crafting.skills"] = {"tool": "tinkering"}
    manifest.params["crafting.deconstruct_skill"] = "salvage"
    host = plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies), ["crafting"]
    )
    used: list[str] = []

    async def skill_used(player_id, skill, chance):
        used.append(skill)

    host.resolvers.define(SKILL_USED, skill_used)
    host.resolvers.define(SKILL_LEVEL, lambda stats, skill: 0)
    return host, used


def _run(host, verb, args):
    session = StubSession("hero")
    asyncio.run(host.registry.get(verb).handler(session, args))
    return session.sent


def test_craft_consumes_parts_yields_a_batch_and_reports_skill(plugin_host, tmp_path):
    host, used = _workshop(plugin_host, tmp_path)
    host.redis.stats["hero"] = {"hp": 4}
    host.redis.inventories["hero"] = _inv("wick", "wick", "tin", "wick")

    listing = _run(host, "recipes", [])[0]
    assert "tin lamp (makes 2) — 2x wick, 1x tin cup  [ready]" in listing
    assert "sword" not in listing  # invalid recipe block reads as absent

    assert _run(host, "craft", ["lamp"])[0] == "You assemble: tin lamp x2."
    assert sorted(it["template"] for it in host.redis.inventories["hero"]) == [
        "lamp",
        "lamp",
        "wick",
    ]
    assert host.redis.stats["hero"]["counters"]["crafted.lamp"] == 1
    assert host.redis.stats["hero"]["hp"] == 4
    assert used == ["tinkering"]

    assert _run(host, "craft", ["lamp"])[0] == "You still need: 1x wick, 1x tin cup."


def test_deconstruct_returns_half_the_recipe(plugin_host, tmp_path):
    host, used = _workshop(plugin_host, tmp_path)
    host.redis.stats["hero"] = {}
    host.redis.inventories["hero"] = [{"id": "l1", "template": "lamp", "name": "tin lamp"}]
    assert _run(host, "deconstruct", ["lamp"])[0] == "You strip the tin lamp down to: 1x wick."
    assert [it["template"] for it in host.redis.inventories["hero"]] == ["wick"]
    assert used == ["salvage"]
