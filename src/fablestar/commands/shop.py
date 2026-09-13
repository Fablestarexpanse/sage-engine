"""Shop commands — buy/sell/browse in rooms that carry a shop block.

The wallet is stats["digi"] (mirrored to the character's digi_balance column
by the PersistenceManager; agents persist it via agent_state). Deterministic:
fixed sell prices from YAML, buy prices = template value * buy_rate.
"""

import logging
import uuid

from fablestar.commands.registry import command
from fablestar.network.session import Session

logger = logging.getLogger(__name__)


async def _shop_here(player_id: str):
    from fablestar.app import app_instance

    room_id = await app_instance.redis.get_player_location(player_id)
    room = app_instance.content_loader.get_room(room_id) if room_id else None
    return (room.shop if room else None), room_id


def _wallet(stats) -> int:
    return int(stats.get("digi", 0) or 0)


def _buy_price(template, shop) -> int:
    return max(1, int(int(template.value or 0) * shop.buy_rate))


LEDGER_CAP = 200


async def _ledger(room_id: str, kind: str, actor: str, item: str, price: int) -> None:
    """Per-shop transaction log (Redis list, newest first, capped)."""
    import json as _json
    import time as _time

    from fablestar.app import app_instance

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
    Payouts floor at zero — the house covers a broke keeper rather than
    blocking trade. Skipped when the keeper trades at their own counter.
    """
    from fablestar.app import app_instance

    if not getattr(shop, "owner", ""):
        return
    try:
        persona = app_instance.content_loader.get_agent_registry().get(shop.owner)
        if persona is None or persona.name == actor:
            return
        stats = await app_instance.redis.get_player_stats(persona.name)
        stats["digi"] = max(0, int(stats.get("digi", 0) or 0) + delta)
        await app_instance.redis.set_player_stats(persona.name, stats)
    except Exception:
        logger.debug("keeper till skipped", exc_info=True)


async def _record_trade(stats, kind: str) -> list:
    from fablestar.app import app_instance

    granted = []
    try:
        from fablestar.achievements.engine import record_counter

        registry = app_instance.content_loader.get_achievement_registry()
        granted += record_counter(stats, registry, "trades")
        granted += record_counter(stats, registry, kind)
    except Exception:
        logger.debug("trade counter skipped", exc_info=True)
    return granted


@command("browse", aliases=["shop", "wares"])
async def browse(session: Session, args: list[str]):
    """See what the shop here sells and buys. Usage: browse"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    shop, _ = await _shop_here(player_id)
    if shop is None:
        await session.send("Nobody here is selling anything.")
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    lines = [f"{shop.name} — you carry {_wallet(stats)} Digi."]
    if shop.sells:
        lines.append("For sale:")
        for entry in shop.sells:
            template = app_instance.content_loader.get_item_template(entry.template)
            name = template.name if template else entry.template
            lines.append(f"  {name} — {entry.price} Digi (buy {name.split()[0].lower()})")
    if shop.buys:
        pct = int(shop.buy_rate * 100)
        lines.append(f"Buying: most goods at {pct}% of value (sell <item>).")
    if not shop.sells and not shop.buys:
        lines.append("The shelves are bare today.")
    await session.send("\r\n".join(lines))


@command("buy")
async def buy(session: Session, args: list[str]):
    """Buy an item from the shop here. Usage: buy <item>"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    if not args:
        await session.send("Buy what? Try 'browse' to see the stock.")
        return
    shop, shop_room_id = await _shop_here(player_id)
    if shop is None or not shop.sells:
        await session.send("Nobody here is selling anything.")
        return

    wanted = " ".join(args).lower()
    entry = None
    for e in shop.sells:
        template = app_instance.content_loader.get_item_template(e.template)
        name = (template.name if template else e.template).lower()
        if wanted in name or wanted in e.template:
            entry = e
            break
    if entry is None:
        await session.send(f"No '{wanted}' for sale here. Try 'browse'.")
        return
    template = app_instance.content_loader.get_item_template(entry.template)
    if template is None:
        await session.send("That stock is mislabeled. The shopkeep apologizes.")
        return

    stats = await app_instance.redis.get_player_stats(player_id)
    if _wallet(stats) < entry.price:
        await session.send(
            f"The {template.name} costs {entry.price} Digi; you carry {_wallet(stats)}."
        )
        return

    stats["digi"] = _wallet(stats) - entry.price
    granted = await _record_trade(stats, "purchases")
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
    await _ledger(shop_room_id, "sale", player_id, template.name, entry.price)
    from fablestar.telemetry import heat, log_event

    log_event(
        "trade", kind="buy", actor=player_id, item=template.id, price=entry.price, room=shop_room_id
    )
    await heat(app_instance.redis, "trades", shop_room_id)
    await _keeper_till(shop, player_id, entry.price)
    await session.send(
        f"You buy the {template.name} for {entry.price} Digi ({stats['digi']} left)."
    )
    from fablestar.achievements.engine import announcement

    for ach in granted:
        await session.send(announcement(ach))


@command("sell")
async def sell(session: Session, args: list[str]):
    """Sell an item to the shop here. Usage: sell <item> | sell all"""
    from fablestar.app import app_instance

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
        to_sell = [it for it in inv if sellable(it)]
    else:
        match = next(
            (it for it in inv if wanted in it.get("name", "").lower() and sellable(it)), None
        )
        to_sell = [match] if match else []
    if not to_sell:
        await session.send(
            "Nothing they'd pay for."
            if wanted == "all"
            else f"You aren't carrying a sellable '{wanted}'."
        )
        return

    total = 0
    sold_names = []
    sold_ids = set()
    for it in to_sell:
        template = app_instance.content_loader.get_item_template(it.get("template", ""))
        price = _buy_price(template, shop)
        total += price
        sold_ids.add(it.get("id"))
        sold_names.append(it.get("name", template.id))
        await _record_trade(stats, "sales")
        await _ledger(shop_room_id, "purchase", player_id, it.get("name", template.id), price)
        await _keeper_till(shop, player_id, -price)

    stats["digi"] = _wallet(stats) + total
    await app_instance.redis.set_player_stats(player_id, stats)
    await app_instance.redis.set_player_inventory(
        player_id, [it for it in inv if it.get("id") not in sold_ids]
    )
    from fablestar.telemetry import heat, log_event

    log_event(
        "trade", kind="sell", actor=player_id, items=len(to_sell), total=total, room=shop_room_id
    )
    await heat(app_instance.redis, "trades", shop_room_id)
    summary = ", ".join(sold_names[:4]) + ("…" if len(sold_names) > 4 else "")
    await session.send(f"You sell {summary} for {total} Digi ({stats['digi']} carried).")


@command("wallet", aliases=["digi", "money"])
async def wallet(session: Session, args: list[str]):
    """Check how much Digi you carry. Usage: wallet"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    await session.send(f"You carry {_wallet(stats)} Digi.")
