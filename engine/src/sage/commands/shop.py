"""Shop commands — buy/sell/browse in rooms that carry a shop block.

Money goes through the engine wallet (the world's primary currency, sage.world.wallet;
agents persist it via agent_state). Deterministic:
fixed sell prices from YAML, buy prices = template value * buy_rate.
"""

import logging
import uuid

from sage.commands.registry import command
from sage.network.session import Session

logger = logging.getLogger(__name__)


async def _shop_here(player_id: str):
    from sage.app import app_instance

    room_id = await app_instance.redis.get_player_location(player_id)
    room = app_instance.content_loader.get_room(room_id) if room_id else None
    return (room.shop if room else None), room_id


def _wallet(stats) -> int:
    from sage.app import app_instance

    return app_instance.wallet.balance(stats)


def _cur() -> str:
    from sage.app import app_instance

    return app_instance.wallet.name()


def _buy_price(template, shop) -> int:
    return max(1, int(int(template.value or 0) * shop.buy_rate))


def resale_price(template, shop) -> int:
    """Secondhand shelf price: value * resale_rate, always above what the shop paid."""
    return max(_buy_price(template, shop) + 1, int(int(template.value or 0) * shop.resale_rate))


def _stock_key(room_id: str) -> str:
    return f"shopstock:{room_id}"


async def secondhand_stock(redis, room_id: str) -> dict[str, int]:
    """template id -> units on the secondhand shelf (zero/negative entries dropped)."""
    raw = await redis.client.hgetall(_stock_key(room_id))
    out = {}
    for k, v in (raw or {}).items():
        k = k.decode() if isinstance(k, bytes) else k
        if int(v) > 0:
            out[k] = int(v)
    return out


LEDGER_CAP = 200


async def _ledger(room_id: str, kind: str, actor: str, item: str, price: int) -> None:
    """Per-shop transaction log (Redis list, newest first, capped)."""
    import json as _json
    import time as _time

    from sage.app import app_instance

    try:
        key = f"shopledger:{room_id}"
        entry = _json.dumps(
            {"at": int(_time.time()), "kind": kind, "actor": actor, "item": item, "price": price}
        )
        client = app_instance.redis.client
        await client.lpush(key, entry)
        await client.ltrim(key, 0, LEDGER_CAP - 1)
    except Exception:
        logger.debug("shop ledger skipped", exc_info=True)


async def _keeper_till(shop, actor: str, delta: int) -> None:
    """Move shop money through the keeper's own wallet when an agent owns it.

    delta > 0: the shop took money in (a sale); delta < 0: it paid out.
    Goes through an atomic Redis counter (digi_pending:<name>) that the agent
    banks on its next tick, so concurrent agent ticks can't lose takings.
    """
    from sage.app import app_instance

    if not getattr(shop, "owner", ""):
        return
    try:
        persona = app_instance.content_loader.get_agent_registry().get(shop.owner)
        if persona is None or persona.name == actor:
            return
        await app_instance.redis.client.incrby(f"digi_pending:{persona.name}", int(delta))
    except Exception:
        logger.debug("keeper till skipped", exc_info=True)


def _is_owner(shop, actor: str) -> bool:
    """Keepers can't trade at their own counter — it minted free money overnight."""
    from sage.app import app_instance

    owner = getattr(shop, "owner", "")
    if not owner:
        return False
    persona = app_instance.content_loader.get_agent_registry().get(owner)
    return persona is not None and persona.name == actor


async def _record_trade(player_id: str, stats, kind: str) -> list[str]:
    from sage.app import app_instance
    from sage.world.counters import count

    return await count(app_instance, player_id, stats, "trades", kind)


@command("browse", aliases=["shop", "wares"])
async def browse(session: Session, args: list[str]):
    """See what the shop here sells and buys. Usage: browse"""
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    shop, shop_room_id = await _shop_here(player_id)
    if shop is None:
        await session.send("Nobody here is selling anything.")
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    lines = [f"{shop.name} — you carry {_wallet(stats)} {_cur()}."]
    if shop.sells:
        lines.append("For sale:")
        for entry in shop.sells:
            template = app_instance.content_loader.get_item_template(entry.template)
            name = template.name if template else entry.template
            lines.append(f"  {name} — {entry.price} {_cur()} (buy {name.split()[0].lower()})")
    if shop.buys:
        used = await secondhand_stock(app_instance.redis, shop_room_id)
        if used:
            lines.append("Secondhand:")
            for tid, count in sorted(used.items()):
                template = app_instance.content_loader.get_item_template(tid)
                if template is None:
                    continue
                lines.append(
                    f"  {template.name} x{count} — {resale_price(template, shop)} {_cur()} each"
                )
        pct = int(shop.buy_rate * 100)
        lines.append(f"Buying: most goods at {pct}% of value (sell <item>).")
    if not shop.sells and not shop.buys:
        lines.append("The shelves are bare today.")
    await session.send("\r\n".join(lines))


@command("buy")
async def buy(session: Session, args: list[str]):
    """Buy an item from the shop here. Usage: buy <item>"""
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    if not args:
        await session.send("Buy what? Try 'browse' to see the stock.")
        return
    shop, shop_room_id = await _shop_here(player_id)
    if shop is None or not (shop.sells or shop.buys):
        await session.send("Nobody here is selling anything.")
        return
    if _is_owner(shop, player_id):
        await session.send("It's your own stock. Taking it off the shelf isn't buying.")
        return

    loader = app_instance.content_loader
    redis = app_instance.redis
    wanted = " ".join(args).lower()

    def matches(template_id: str) -> bool:
        template = loader.get_item_template(template_id)
        name = (template.name if template else template_id).lower()
        return wanted in name or wanted in template_id

    # Cheapest match across fixed stock and the secondhand shelf (a used
    # blade at 18 must beat a new one at 25).
    offers: list[tuple[int, object, bool]] = []
    entry = next((e for e in shop.sells if matches(e.template)), None)
    if entry is not None:
        fixed = loader.get_item_template(entry.template)
        if fixed is not None:
            offers.append((entry.price, fixed, False))
    if shop.buys:
        shelf = await secondhand_stock(redis, shop_room_id)
        tid = next((t for t in sorted(shelf) if matches(t)), None)
        used = loader.get_item_template(tid) if tid else None
        if used is not None:
            offers.append((resale_price(used, shop), used, True))
    template, price, from_shelf = None, 0, False
    if offers:
        price, template, from_shelf = min(offers, key=lambda o: o[0])
    if template is None:
        await session.send(f"No '{wanted}' for sale here. Try 'browse'.")
        return

    stats = await redis.get_player_stats(player_id)
    if _wallet(stats) < price:
        await session.send(
            f"The {template.name} costs {price} {_cur()}; you carry {_wallet(stats)}."
        )
        return

    if from_shelf:
        # Atomic reserve: two buyers can't both take the last unit.
        left = await redis.client.hincrby(_stock_key(shop_room_id), template.id, -1)
        if left < 0:
            await redis.client.hincrby(_stock_key(shop_room_id), template.id, 1)
            await session.send(f"Someone just bought the last {template.name}.")
            return

    entry_price = price
    app_instance.wallet.debit(stats, price)
    trade_lines = await _record_trade(player_id, stats, "purchases")
    inv = await app_instance.redis.get_player_inventory(player_id)
    inv.append(
        {
            "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
            "template": template.id,
            "name": template.name,
            "description": template.description,
            "value": template.value,
        }
    )
    await app_instance.redis.set_player_stats(player_id, stats)
    await app_instance.redis.set_player_inventory(player_id, inv)
    await _ledger(shop_room_id, "sale", player_id, template.name, entry_price)
    from sage.telemetry import heat, log_event

    log_event(
        "trade",
        direction="buy",
        actor=player_id,
        item=template.id,
        price=entry_price,
        room=shop_room_id,
    )
    await heat(app_instance.redis, "trades", shop_room_id)
    await _keeper_till(shop, player_id, entry_price)
    await session.send(
        f"You buy the {template.name} for {entry_price} {_cur()} ({_wallet(stats)} left)."
    )
    for line in trade_lines:
        await session.send(line)


@command("sell")
async def sell(session: Session, args: list[str]):
    """Sell an item to the shop here. Usage: sell <item> | sell all"""
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    if not args:
        await session.send("Sell what? Usage: sell <item> (or 'sell all').")
        return
    shop, shop_room_id = await _shop_here(player_id)
    if shop is None or not shop.buys:
        await session.send("Nobody here is buying.")
        return
    if _is_owner(shop, player_id):
        await session.send("You can't sell to your own till. Take it to another buyer.")
        return

    inv = await app_instance.redis.get_player_inventory(player_id)
    stats = await app_instance.redis.get_player_stats(player_id)
    equipped_ids = {(it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it}

    wanted = " ".join(args).lower()

    def sellable(it):
        if it.get("id") in equipped_ids:
            return False
        template = app_instance.content_loader.get_item_template(it.get("template", ""))
        return template is not None and int(template.value or 0) > 0

    if wanted == "all":
        candidates = [it for it in inv if sellable(it)]
    else:
        match = next(
            (it for it in inv if wanted in it.get("name", "").lower() and sellable(it)), None
        )
        candidates = [match] if match else []
    if not candidates:
        await session.send(
            "Nothing they'd pay for."
            if wanted == "all"
            else f"You aren't carrying a sellable '{wanted}'."
        )
        return

    # Goods go onto the secondhand shelf until it holds stock_cap of that item;
    # past that the shop is overstocked: it still buys (so packs never clog)
    # but at half its rate, and the unit is scrapped rather than shelved.
    shelf = await secondhand_stock(app_instance.redis, shop_room_id)
    to_sell = candidates
    overstock_ids: set[str] = set()
    for it in to_sell:
        tid = it.get("template", "")
        if shelf.get(tid, 0) >= shop.stock_cap:
            overstock_ids.add(it.get("id"))
        else:
            shelf[tid] = shelf.get(tid, 0) + 1

    total = 0
    sold_names = []
    sold_ids = set()
    for it in to_sell:
        template = app_instance.content_loader.get_item_template(it.get("template", ""))
        overstocked = it.get("id") in overstock_ids
        price = (
            max(1, _buy_price(template, shop) // 2) if overstocked else _buy_price(template, shop)
        )
        total += price
        sold_ids.add(it.get("id"))
        sold_names.append(it.get("name", template.id))
        await _record_trade(player_id, stats, "sales")
        await _ledger(shop_room_id, "purchase", player_id, it.get("name", template.id), price)
        await _keeper_till(shop, player_id, -price)
        if not overstocked:
            await app_instance.redis.client.hincrby(_stock_key(shop_room_id), template.id, 1)

    app_instance.wallet.credit(stats, total)
    await app_instance.redis.set_player_stats(player_id, stats)
    await app_instance.redis.set_player_inventory(
        player_id, [it for it in inv if it.get("id") not in sold_ids]
    )
    from sage.telemetry import heat, log_event

    log_event(
        "trade",
        direction="sell",
        actor=player_id,
        items=len(to_sell),
        total=total,
        room=shop_room_id,
    )
    await heat(app_instance.redis, "trades", shop_room_id)
    summary = ", ".join(sold_names[:4]) + ("…" if len(sold_names) > 4 else "")
    await session.send(f"You sell {summary} for {total} {_cur()} ({_wallet(stats)} carried).")
    if overstock_ids:
        await session.send("The shelves are overflowing — some of that went for half price.")


@command("wallet", aliases=["digi", "money"])
async def wallet(session: Session, args: list[str]):
    """Check how much money you carry. Usage: wallet"""
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    await session.send(f"You carry {_wallet(stats)} {_cur()}.")
