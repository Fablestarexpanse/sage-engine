"""Secondhand resale pricing: the shelf always sells above what the shop paid."""

from fablestar.commands.shop import _buy_price, resale_price
from fablestar.world.models import ItemTemplate, ShopModel

PAWN = ShopModel(name="pawn", buys=True, buy_rate=0.5)


def test_resale_at_full_value_by_default():
    cell = ItemTemplate(id="power_cell", name="power cell", value=12)
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
