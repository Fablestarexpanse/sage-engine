"""Consumables through the host: `use` heals up to max, counts use, and refuses non-consumables."""

from __future__ import annotations

import asyncio

from tests.fakes import StubSession, repo_world

ITEMS = {
    "tonic": "id: tonic\nname: bitter tonic\nheal: 8\n",
    "stone": "id: stone\nname: river stone\n",
}


def _host(plugin_host, tmp_path):
    items = tmp_path / "content" / "world" / "items"
    items.mkdir(parents=True)
    for slug, body in ITEMS.items():
        (items / f"{slug}.yaml").write_text(body, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    content_override = tmp_path / "content"
    return plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies, content_override),
        ["consumables"],
    )


def _run(host, session, *args):
    asyncio.run(host.registry.get("use").handler(session, list(args)))


def test_use_heals_to_max_counts_and_consumes(plugin_host, tmp_path):
    host = _host(plugin_host, tmp_path)
    session = StubSession("hero")
    host.redis.stats["hero"] = {"hp": 15, "max_hp": 20}
    host.redis.inventories["hero"] = [
        {"id": "t1", "template": "tonic", "name": "bitter tonic"},
        {"id": "s1", "template": "stone", "name": "river stone"},
    ]

    _run(host, session)
    assert "Use what?" in session.sent[-1]
    _run(host, session, "stone")
    assert "river stone" in session.sent[-1]
    _run(host, session, "tonic")
    assert "+5 hp, 20/20" in session.sent[-1]
    stats = host.redis.stats["hero"]
    assert stats["hp"] == 20
    assert stats["counters"]["items_used"] == 1 and stats["counters"]["items_used.tonic"] == 1
    assert [it["id"] for it in host.redis.inventories["hero"]] == ["s1"]
    _run(host, session, "tonic")
    assert "aren't carrying" in session.sent[-1]

    service = host.services["consumables"][1]
    assert service.heal_of(host.content.get_item_template("tonic")) == 8
    assert service.heal_of(host.content.get_item_template("stone")) == 0
