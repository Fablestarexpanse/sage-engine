"""Shop plugin: pricing rules, and trading through the real host."""

import asyncio

from sage_plugin_shop.models import ShopModel, resale_price
from sage_plugin_shop.models import buy_price as _buy_price

from sage.world.models import ItemTemplate
from tests.fakes import StubSession, repo_world

PAWN = ShopModel(name="pawn", buys=True, buy_rate=0.5)


def test_resale_at_full_value_by_default():
    cell = ItemTemplate(id="cell", name="cell", value=12)
    assert _buy_price(cell, PAWN) == 6
    assert resale_price(cell, PAWN) == 12


def test_resale_never_at_or_below_buy_price():
    cheap = ItemTemplate(id="scrap", name="scrap", value=1)
    assert resale_price(cheap, PAWN) > _buy_price(cheap, PAWN)
    stingy = ShopModel(name="s", buys=True, buy_rate=0.5, resale_rate=0.4)
    item = ItemTemplate(id="x", name="x", value=20)
    assert resale_price(item, stingy) == _buy_price(item, stingy) + 1


def test_stock_cap_defaults():
    assert PAWN.stock_cap == 20
    assert ShopModel(name="s", stock_cap=0).stock_cap == 0


def _trade(host, verb, player, args):
    session = StubSession(player)
    asyncio.run(host.registry.get(verb).handler(session, args))
    return session.sent


PAWN_ROOM = """id: town:pawn
zone: town
type: hub
shop: {name: Pawn, buys: true, buy_rate: 0.5, owner: Keeper Kim}
"""

BAKERY_ROOM = """id: town:bakery
zone: town
type: hub
shop: {name: Bakery, owner: Baker Bo, sells: [{template: bun, price: 8}]}
"""


def _market_world(tmp_path):
    """The repo world's manifest over a two-shop test content tree."""
    content = tmp_path / "content"
    items = content / "world" / "items"
    rooms = content / "world" / "zones" / "town" / "rooms"
    items.mkdir(parents=True)
    rooms.mkdir(parents=True)
    (items / "lamp.yaml").write_text("id: lamp\nname: brass lamp\nvalue: 12\n", encoding="utf-8")
    (items / "bun.yaml").write_text("id: bun\nname: sweet bun\nvalue: 6\n", encoding="utf-8")
    (rooms / "pawn.yaml").write_text(PAWN_ROOM, encoding="utf-8")
    (rooms / "bakery.yaml").write_text(BAKERY_ROOM, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    content_override = content
    return type(world)(world.root, manifest, world.stats, world.currencies, content_override)


def test_buy_and_sell_move_money_goods_counters_and_pay_the_keeper(plugin_host, tmp_path):
    host = plugin_host(_market_world(tmp_path), ["shop"])
    key = host.world.currencies[0].key
    host.redis.locations["hero"] = "town:pawn"
    host.redis.stats["hero"] = {key: 30, "hp": 10}
    host.redis.inventories["hero"] = [{"id": "l1", "template": "lamp", "name": "brass lamp"}]

    sold = _trade(host, "sell", "hero", ["lamp"])
    assert sold[0].startswith("You sell brass lamp for 6 ")
    assert host.redis.stats["hero"][key] == 36
    assert host.redis.inventories["hero"] == []
    assert host.redis.client.hashes["shopstock:town:pawn"] == {"lamp": "1"}
    assert host.redis.client.strings["wallet_pending:Keeper Kim"] == "-6"

    bought = _trade(host, "buy", "hero", ["lamp"])  # secondhand shelf, resale at full value
    assert bought[0].startswith("You buy the brass lamp for 12 ")
    stats = host.redis.stats["hero"]
    assert stats[key] == 24 and stats["hp"] == 10
    assert stats["counters"]["trades"] == 2 and stats["counters"]["purchases"] == 1
    assert host.redis.client.strings["wallet_pending:Keeper Kim"] == "6"
    assert len(host.redis.client.lists["shopledger:town:pawn"]) == 2


def test_broke_buyers_and_keepers_at_their_own_counter_are_refused(plugin_host, tmp_path):
    host = plugin_host(_market_world(tmp_path), ["shop"])
    key = host.world.currencies[0].key
    host.redis.locations["hero"] = "town:bakery"
    host.redis.stats["hero"] = {key: 3}
    assert "costs 8" in _trade(host, "buy", "hero", ["bun"])[0]
    assert host.redis.stats["hero"][key] == 3

    host.redis.locations["Baker Bo"] = "town:bakery"
    host.redis.stats["Baker Bo"] = {key: 100}
    assert "your own stock" in _trade(host, "buy", "Baker Bo", ["bun"])[0]


def test_keeper_banks_takings_through_the_wallet(plugin_host, tmp_path):
    host = plugin_host(_market_world(tmp_path), ["shop"])
    key = host.world.currencies[0].key
    host.redis.locations["hero"] = "town:bakery"
    host.redis.stats["hero"] = {key: 20}
    _trade(host, "buy", "hero", ["bun"])
    api = next(r.api for r in host.loaded if r.id == "shop")
    keeper = {key: 1}
    assert asyncio.run(api.wallet.bank_pending("Baker Bo", keeper)) == 8
    assert keeper[key] == 9
    assert asyncio.run(api.wallet.bank_pending("Baker Bo", keeper)) == 0


def test_wallet_aliases_come_from_the_world(plugin_host, tmp_path):
    host = plugin_host(_market_world(tmp_path), ["shop"])
    aliases = host.world.param("shop.wallet_aliases", ["money"])
    assert all(host.registry.get(a) is not None for a in aliases)
