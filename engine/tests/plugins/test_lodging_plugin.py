"""Lodging plugin: lease rules, renting through the real host, and the lease sweep."""

import asyncio
import json

from sage_plugin_lodging.leases import LodgingModel, free_rooms, parse_rentals

from tests.fakes import StubSession, repo_world

LODGING = LodgingModel(rooms=["z:a", "z:b"], price=8, lease_minutes=60)

DESK_ROOM = """id: town:desk
zone: town
type: hub
lodging: {name: the Inn, rooms: ["town:bed_a", "town:bed_b"], price: 8, lease_minutes: 60}
"""


def test_free_rooms_counts_lapsed_leases_as_free():
    rentals = {"z:a": {"tenant": "x", "until": 50.0}, "z:b": {"tenant": "y", "until": 500.0}}
    assert free_rooms(LODGING, rentals, now=100.0) == ["z:a"]


def test_free_rooms_all_free_when_unrented():
    assert free_rooms(LODGING, {}, now=100.0) == ["z:a", "z:b"]


def test_legacy_plain_rental_values_read_as_expired():
    rentals = parse_rentals(
        {b"z:a": b"Old Tenant", b"z:b": json.dumps({"tenant": "M", "until": 9e9})}
    )
    assert rentals["z:a"] == {"tenant": "Old Tenant", "until": 0}
    assert free_rooms(LODGING, rentals, now=100.0) == ["z:a"]


def _inn_world(tmp_path):
    rooms = tmp_path / "content" / "world" / "zones" / "town" / "rooms"
    rooms.mkdir(parents=True)
    (rooms / "desk.yaml").write_text(DESK_ROOM, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    content_override = tmp_path / "content"
    return type(world)(world.root, manifest, world.stats, world.currencies, content_override)


def _rent(host, player):
    session = StubSession(player)
    asyncio.run(host.registry.get("rent").handler(session, []))
    return session.sent


def test_rent_takes_money_sets_home_and_refuses_early_renewal(plugin_host, tmp_path):
    host = plugin_host(_inn_world(tmp_path), ["lodging"])
    key = host.world.currencies[0].key
    host.redis.locations["hero"] = "town:desk"
    host.redis.stats["hero"] = {key: 20, "hp": 5}

    assert _rent(host, "hero")[0].startswith("The keeper hands you the key to bed_a")
    stats = host.redis.stats["hero"]
    assert stats[key] == 12 and stats["home_room"] == "town:bed_a" and stats["hp"] == 5
    assert stats["counters"]["rent_paid"] == 1
    lease = json.loads(host.redis.client.hashes["rentals"]["town:bed_a"])
    assert lease["tenant"] == "hero"

    assert "Come back when it's nearly up" in _rent(host, "hero")[0]
    assert host.redis.stats["hero"][key] == 12


def test_full_desk_and_broke_tenants_are_refused(plugin_host, tmp_path):
    host = plugin_host(_inn_world(tmp_path), ["lodging"])
    key = host.world.currencies[0].key
    for name in ("a", "b"):
        host.redis.locations[name] = "town:desk"
        host.redis.stats[name] = {key: 50}
        _rent(host, name)
    host.redis.locations["late"] = "town:desk"
    host.redis.stats["late"] = {key: 50}
    assert "is full" in _rent(host, "late")[0]

    host.redis.client.hashes["rentals"].clear()
    host.redis.stats["late"] = {key: 3}
    assert "A room here runs 8" in _rent(host, "late")[0]


def test_lease_sweep_clears_lapsed_homes(plugin_host, tmp_path):
    host = plugin_host(_inn_world(tmp_path), ["lodging"])
    key = host.world.currencies[0].key
    host.redis.locations["hero"] = "town:desk"
    host.redis.stats["hero"] = {key: 20}
    _rent(host, "hero")
    service = host.services["lodging"][1]
    expired = asyncio.run(service.expire_leases(now=9e12))
    assert expired == [("town:bed_a", "hero")]
    assert "home_room" not in host.redis.stats["hero"]
    assert host.redis.client.hashes["rentals"] == {}
