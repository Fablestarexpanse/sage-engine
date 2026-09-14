"""Shop plugin: browse/buy/sell at rooms with a `shop:` block, the wallet command, and the admin
Shops ledger view. Deterministic: fixed sell prices from YAML, buy prices = value * buy_rate."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter

from sage.api import PluginAPI

from .models import ShopModel, buy_price, resale_price

LEDGER_CAP = 200


def stock_key(room_id: str) -> str:
    return f"shopstock:{room_id}"


def ledger_key(room_id: str) -> str:
    return f"shopledger:{room_id}"


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else value


class ShopService:
    """What other systems (agents) may ask about shops."""

    def __init__(self, api: PluginAPI):
        self._api = api

    def at(self, room_id: str | None) -> ShopModel | None:
        if not room_id:
            return None
        room = self._api.content.room(room_id)
        return self._api.content.extension(room, "room", "shop") if room else None


def setup(api: PluginAPI) -> None:
    api.content.extend("room", "shop", ShopModel)
    service = ShopService(api)
    wallet = api.wallet

    async def shop_here(player_id: str) -> tuple[ShopModel | None, str | None]:
        room_id = await api.state.location(player_id)
        return service.at(room_id), room_id

    async def secondhand_stock(room_id: str) -> dict[str, int]:
        """template id -> units on the secondhand shelf (zero/negative entries dropped)."""
        raw = await api.redis.hgetall(stock_key(room_id))
        return {_text(k): int(v) for k, v in (raw or {}).items() if int(v) > 0}

    async def ledger(room_id: str, kind: str, actor: str, item: str, price: int) -> None:
        """Per-shop transaction log (newest first, capped)."""
        try:
            entry = json.dumps(
                {"at": int(time.time()), "kind": kind, "actor": actor, "item": item, "price": price}
            )
            await api.redis.lpush(ledger_key(room_id), entry)
            await api.redis.ltrim(ledger_key(room_id), 0, LEDGER_CAP - 1)
        except Exception:
            api.log.debug("shop ledger skipped", exc_info=True)

    async def keeper_till(shop: ShopModel, actor: str, delta: int) -> None:
        """Shop money moves through the keeper's wallet (banked on their side, race-free)."""
        if not shop.owner or shop.owner == actor:
            return
        try:
            await wallet.pay_later(shop.owner, delta)
        except Exception:
            api.log.debug("keeper till skipped", exc_info=True)

    async def browse(session, args) -> None:
        """See what the shop here sells and buys. Usage: browse"""
        shop, room_id = await shop_here(session.player_id)
        if shop is None:
            await session.send(api.t("shop.nobody_selling"))
            return
        stats = await api.state.snapshot(session.player_id)
        currency = wallet.name()
        lines = [
            api.t(
                "shop.browse_header",
                shop=shop.name,
                money=wallet.balance(stats),
                currency=currency,
            )
        ]
        if shop.sells:
            lines.append(api.t("shop.for_sale"))
            for entry in shop.sells:
                template = api.content.item_template(entry.template)
                name = template.name if template else entry.template
                lines.append(
                    api.t(
                        "shop.stock_entry",
                        name=name,
                        price=entry.price,
                        currency=currency,
                        keyword=name.split()[0].lower(),
                    )
                )
        if shop.buys:
            used = await secondhand_stock(room_id)
            if used:
                lines.append(api.t("shop.secondhand"))
                for tid, count in sorted(used.items()):
                    template = api.content.item_template(tid)
                    if template is None:
                        continue
                    lines.append(
                        api.t(
                            "shop.secondhand_entry",
                            name=template.name,
                            count=count,
                            price=resale_price(template, shop),
                            currency=currency,
                        )
                    )
            lines.append(api.t("shop.buying", percent=int(shop.buy_rate * 100)))
        if not shop.sells and not shop.buys:
            lines.append(api.t("shop.bare"))
        await session.send("\r\n".join(lines))

    async def buy(session, args) -> None:
        """Buy an item from the shop here. Usage: buy <item>"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("shop.buy_what"))
            return
        shop, room_id = await shop_here(player_id)
        if shop is None or not (shop.sells or shop.buys):
            await session.send(api.t("shop.nobody_selling"))
            return
        if shop.owner == player_id:
            await session.send(api.t("shop.own_stock"))
            return
        wanted = " ".join(args).lower()

        def matches(template_id: str) -> bool:
            template = api.content.item_template(template_id)
            name = (template.name if template else template_id).lower()
            return wanted in name or wanted in template_id

        # Cheapest match across fixed stock and the secondhand shelf (a used
        # blade at 18 must beat a new one at 25).
        offers: list[tuple[int, Any, bool]] = []
        entry = next((e for e in shop.sells if matches(e.template)), None)
        if entry is not None:
            fixed = api.content.item_template(entry.template)
            if fixed is not None:
                offers.append((entry.price, fixed, False))
        if shop.buys:
            shelf = await secondhand_stock(room_id)
            tid = next((t for t in sorted(shelf) if matches(t)), None)
            used = api.content.item_template(tid) if tid else None
            if used is not None:
                offers.append((resale_price(used, shop), used, True))
        if not offers:
            await session.send(api.t("shop.not_for_sale", wanted=wanted))
            return
        price, template, from_shelf = min(offers, key=lambda o: o[0])

        currency = wallet.name()
        async with api.state.edit(player_id) as stats:
            if wallet.balance(stats) < price:
                await session.send(
                    api.t(
                        "shop.too_poor",
                        item=template.name,
                        price=price,
                        currency=currency,
                        money=wallet.balance(stats),
                    )
                )
                return
            if from_shelf:
                # Atomic reserve: two buyers can't both take the last unit.
                left = await api.redis.hincrby(stock_key(room_id), template.id, -1)
                if left < 0:
                    await api.redis.hincrby(stock_key(room_id), template.id, 1)
                    await session.send(api.t("shop.sold_out", item=template.name))
                    return
            wallet.debit(stats, price)
            trade_lines = await api.counters.count(player_id, stats, "trades", "purchases")
            inventory = await api.inventory.get(player_id)
            inventory.append(
                {
                    "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
                    "template": template.id,
                    "name": template.name,
                    "description": template.description,
                    "value": template.value,
                }
            )
            await api.inventory.set(player_id, inventory)
            money_left = wallet.balance(stats)
        await ledger(room_id, "sale", player_id, template.name, price)
        api.telemetry.event(
            "trade", direction="buy", actor=player_id, item=template.id, price=price, room=room_id
        )
        await api.telemetry.heat("trades", room_id)
        await keeper_till(shop, player_id, price)
        await session.send(
            api.t(
                "shop.bought", item=template.name, price=price, currency=currency, money=money_left
            )
        )
        for line in trade_lines:
            await session.send(line)

    async def sell(session, args) -> None:
        """Sell an item to the shop here. Usage: sell <item> | sell all"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("shop.sell_what"))
            return
        shop, room_id = await shop_here(player_id)
        if shop is None or not shop.buys:
            await session.send(api.t("shop.nobody_buying"))
            return
        if shop.owner == player_id:
            await session.send(api.t("shop.own_till"))
            return
        wanted = " ".join(args).lower()

        async with api.state.edit(player_id) as stats:
            inventory = await api.inventory.get(player_id)
            equipped = {
                (it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it
            }

            def sellable(it: dict[str, Any]) -> bool:
                if it.get("id") in equipped:
                    return False
                template = api.content.item_template(it.get("template", ""))
                return template is not None and int(template.value or 0) > 0

            if wanted == "all":
                candidates = [it for it in inventory if sellable(it)]
            else:
                match = next(
                    (
                        it
                        for it in inventory
                        if wanted in it.get("name", "").lower() and sellable(it)
                    ),
                    None,
                )
                candidates = [match] if match else []
            if not candidates:
                await session.send(
                    api.t("shop.nothing_wanted")
                    if wanted == "all"
                    else api.t("shop.not_carrying", wanted=wanted)
                )
                return

            # Goods go onto the secondhand shelf until it holds stock_cap of that item;
            # past that the shop is overstocked: it still buys (so packs never clog)
            # but at half its rate, and the unit is scrapped rather than shelved.
            shelf = await secondhand_stock(room_id)
            overstock_ids: set[str] = set()
            for it in candidates:
                tid = it.get("template", "")
                if shelf.get(tid, 0) >= shop.stock_cap:
                    overstock_ids.add(it.get("id"))
                else:
                    shelf[tid] = shelf.get(tid, 0) + 1

            total = 0
            sold_names: list[str] = []
            sold_ids: set[str] = set()
            for it in candidates:
                template = api.content.item_template(it.get("template", ""))
                overstocked = it.get("id") in overstock_ids
                price = (
                    max(1, buy_price(template, shop) // 2)
                    if overstocked
                    else buy_price(template, shop)
                )
                total += price
                sold_ids.add(it.get("id"))
                sold_names.append(it.get("name", template.id))
                await api.counters.count(player_id, stats, "trades", "sales")
                await ledger(room_id, "purchase", player_id, it.get("name", template.id), price)
                await keeper_till(shop, player_id, -price)
                if not overstocked:
                    await api.redis.hincrby(stock_key(room_id), template.id, 1)

            wallet.credit(stats, total)
            await api.inventory.set(
                player_id, [it for it in inventory if it.get("id") not in sold_ids]
            )
            money = wallet.balance(stats)
        api.telemetry.event(
            "trade",
            direction="sell",
            actor=player_id,
            items=len(candidates),
            total=total,
            room=room_id,
        )
        await api.telemetry.heat("trades", room_id)
        summary = ", ".join(sold_names[:4]) + ("…" if len(sold_names) > 4 else "")
        await session.send(
            api.t("shop.sold", items=summary, total=total, currency=wallet.name(), money=money)
        )
        if overstock_ids:
            await session.send(api.t("shop.overstocked"))

    async def show_wallet(session, args) -> None:
        """Check how much money you carry. Usage: wallet"""
        stats = await api.state.snapshot(session.player_id)
        await session.send(
            api.t("shop.wallet", money=wallet.balance(stats), currency=wallet.name())
        )

    admin = APIRouter()

    @admin.get("/shops")
    async def shops_list() -> list[dict[str, Any]]:
        rows = []
        for room_id in api.content.room_ids():
            shop = service.at(room_id)
            if shop is None:
                continue
            entries = []
            sold_count = revenue = bought_count = spend = 0
            try:
                for raw in await api.redis.lrange(ledger_key(room_id), 0, LEDGER_CAP - 1) or []:
                    try:
                        e = json.loads(_text(raw))
                    except ValueError:
                        continue
                    entries.append(e)
                    if e.get("kind") == "sale":
                        sold_count += 1
                        revenue += int(e.get("price", 0))
                    elif e.get("kind") == "purchase":
                        bought_count += 1
                        spend += int(e.get("price", 0))
            except Exception:
                api.log.debug("shop ledger read failed for %s", room_id, exc_info=True)

            owner = None
            if shop.owner:
                location = await api.state.location(shop.owner)
                owner = {"id": shop.owner, "name": shop.owner, "money": None, "room_id": location}
                if location:
                    stats = await api.state.snapshot(shop.owner)
                    carried = await api.inventory.get(shop.owner)
                    owner.update(
                        money=wallet.balance(stats),
                        home_room=stats.get("home_room"),
                        inventory=[it.get("name", "?") for it in carried],
                    )
            stock = []
            for entry in shop.sells:
                template = api.content.item_template(entry.template)
                stock.append(
                    {
                        "template": entry.template,
                        "name": template.name if template else entry.template,
                        "price": entry.price,
                    }
                )
            secondhand = []
            if shop.buys:
                for tid, count in sorted((await secondhand_stock(room_id)).items()):
                    template = api.content.item_template(tid)
                    if template is not None:
                        secondhand.append(
                            {
                                "template": tid,
                                "name": template.name,
                                "count": count,
                                "price": resale_price(template, shop),
                            }
                        )
            rows.append(
                {
                    "room_id": room_id,
                    "shop_name": shop.name,
                    "currency": wallet.name(),
                    "owner": owner,
                    "stock": stock,
                    "secondhand": secondhand,
                    "stock_cap": shop.stock_cap,
                    "buys": shop.buys,
                    "buy_rate": shop.buy_rate,
                    "sold_count": sold_count,
                    "revenue": revenue,
                    "bought_count": bought_count,
                    "spend": spend,
                    "ledger": entries[:30],
                }
            )
        return rows

    api.commands.register("browse", browse, aliases=["shop", "wares"])
    api.commands.register("buy", buy)
    api.commands.register("sell", sell)
    api.commands.register(
        "wallet", show_wallet, aliases=list(api.param("wallet_aliases", ["money"]))
    )
    api.services.provide("shop", service)
    api.http.admin_router(admin, tool="shops")
