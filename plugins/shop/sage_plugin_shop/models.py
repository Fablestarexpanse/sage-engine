"""The `shop:` block a room may carry, and the pricing rules that read it."""

from typing import Any

from pydantic import BaseModel, Field


class ShopStockModel(BaseModel):
    template: str
    price: int = Field(gt=0)


class ShopModel(BaseModel):
    """A room that trades: fixed sell stock, and optionally buys items for a
    fraction of their template value."""

    name: str = "the shop"
    sells: list[ShopStockModel] = Field(default_factory=list)
    buys: bool = False
    buy_rate: float = Field(default=0.5, gt=0, le=1.0)
    # Goods a buying shop takes in go onto a secondhand shelf and resell at
    # template value * resale_rate (never below the buy price + 1).
    resale_rate: float = Field(default=1.0, gt=0)
    # Max secondhand units per item type; past it the shop pays half and scraps the unit.
    stock_cap: int = Field(default=20, ge=0)
    # Character name of the keeper: sales pay them, and they can't trade at their own counter.
    owner: str = ""


def buy_price(template: Any, shop: ShopModel) -> int:
    """What the shop pays for one unit."""
    return max(1, int(int(template.value or 0) * shop.buy_rate))


def resale_price(template: Any, shop: ShopModel) -> int:
    """Secondhand shelf price: value * resale_rate, always above what the shop paid."""
    return max(buy_price(template, shop) + 1, int(int(template.value or 0) * shop.resale_rate))
