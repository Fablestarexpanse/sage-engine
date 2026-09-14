"""Staff tools for one player character: find, inspect, move, set money, give or remove items, kick.

A character's live state lives in Redis once it has logged in since Redis was last cleared (its
location key exists), and the persistence flush copies Redis over Postgres about every minute.
So every write here updates Redis when that state exists, as well as the Postgres row. A write to
Postgres alone would be silently undone by the next flush.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select


class CharacterToolError(ValueError):
    """A request the tools refuse: unknown room, currency or item, or a bad amount."""


async def _hot_room(server: Any, name: str) -> str | None:
    try:
        return await server.redis.get_player_location(name)
    except Exception:
        return None


def _session(server: Any, name: str) -> Any:
    try:
        return server.session_manager.get_session_by_player(name)
    except Exception:
        return None


async def _row(session: Any, character_id: int) -> Any:
    from sage.state.models import Character

    char = await session.get(Character, character_id)
    if char is None:
        raise LookupError("character_not_found")
    return char


async def find(server: Any, query: str, limit: int = 25) -> list[dict[str, Any]]:
    from sage.state.models import Account, Character

    q = (query or "").strip().lower()
    stmt = (
        select(Character, Account)
        .join(Account, Account.id == Character.account_id)
        .order_by(Character.name)
        .limit(max(1, min(limit, 100)))
    )
    if q:
        stmt = stmt.where(
            func.lower(Character.name).contains(q) | func.lower(Account.username).contains(q)
        )
    async with server.db.session_factory() as session:
        rows = (await session.execute(stmt)).all()
    out = []
    for char, account in rows:
        hot = await _hot_room(server, char.name)
        out.append(
            {
                "id": char.id,
                "name": char.name,
                "account_id": account.id,
                "account": account.username,
                "room_id": hot or char.room_id,
                "online": _session(server, char.name) is not None,
                "suspended": account.suspended_at is not None,
            }
        )
    return out


async def detail(server: Any, character_id: int) -> dict[str, Any]:
    """The character as the game sees it now: live state when it exists, else the saved row."""
    from sage.state.models import Account

    async with server.db.session_factory() as session:
        char = await _row(session, character_id)
        account = await session.get(Account, char.account_id)
    hot = await _hot_room(server, char.name)
    stats = await server.redis.get_player_stats(char.name) if hot else None
    inventory = await server.redis.get_player_inventory(char.name) if hot else None
    stats = stats if stats else dict(char.stats or {})
    inventory = inventory if inventory is not None else list(char.inventory or [])
    wallet = server.wallet
    currencies = [
        {"key": c.key, "name": wallet.name(c.key), "balance": wallet.balance(stats, c.key)}
        for c in getattr(server.world, "currencies", []) or []
    ]
    return {
        "id": char.id,
        "name": char.name,
        "account_id": char.account_id,
        "account": account.username if account else None,
        "suspended": bool(account and account.suspended_at),
        "online": _session(server, char.name) is not None,
        "live_state": bool(hot),
        "room_id": hot or char.room_id,
        "hp": stats.get("hp"),
        "max_hp": stats.get("max_hp"),
        "currencies": currencies,
        "inventory": inventory,
    }


async def _write(
    server: Any,
    character_id: int,
    *,
    room_id: str | None = None,
    stats: dict[str, Any] | None = None,
    inventory: list[dict[str, Any]] | None = None,
) -> str:
    """Save to Postgres and, when the character has live state, to Redis. Returns the name."""
    async with server.db.session_factory() as session:
        char = await _row(session, character_id)
        name = char.name
        if room_id is not None:
            char.room_id = room_id
        if stats is not None:
            char.stats = stats
        if inventory is not None:
            char.inventory = inventory
        await session.commit()
    if await _hot_room(server, name):
        if room_id is not None:
            await _relocate(server, name, room_id)
        if stats is not None:
            await server.redis.set_player_stats(name, stats)
        if inventory is not None:
            await server.redis.set_player_inventory(name, inventory)
    return name


async def _relocate(server: Any, name: str, room_id: str) -> None:
    """Connected characters join the room's player set; offline ones only get the location key."""
    if _session(server, name) is not None:
        await server.redis.set_player_location(name, room_id)
    else:
        await server.redis.set_player_location_offline(name, room_id)


async def _current(
    server: Any, character_id: int
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    async with server.db.session_factory() as session:
        char = await _row(session, character_id)
        name, stats, inventory = char.name, dict(char.stats or {}), list(char.inventory or [])
    if await _hot_room(server, name):
        stats = await server.redis.get_player_stats(name) or stats
        live_inventory = await server.redis.get_player_inventory(name)
        inventory = list(live_inventory) if live_inventory is not None else inventory
    return name, stats, inventory


async def _tell(server: Any, name: str, key: str, **values: Any) -> None:
    session = _session(server, name)
    if session is not None:
        try:
            await session.say(key, **values)
        except Exception:
            pass


async def move(server: Any, character_id: int, room_id: str) -> dict[str, Any]:
    room_id = (room_id or "").strip()
    if server.content_loader.get_room(room_id) is None:
        raise CharacterToolError(f"room_not_found: {room_id}")
    name = await _write(server, character_id, room_id=room_id)
    session = _session(server, name)
    if session is not None:
        await _tell(server, name, "staff.moved")
        try:
            await server.dispatcher.dispatch(session, "look")
        except Exception:
            pass
    return {"name": name, "room_id": room_id}


async def set_balance(server: Any, character_id: int, currency: str, amount: int) -> dict[str, Any]:
    from sage.world.wallet import WalletError

    if not isinstance(amount, int) or amount < 0:
        raise CharacterToolError("amount must be a whole number, 0 or more")
    name, stats, _ = await _current(server, character_id)
    try:
        before = server.wallet.balance(stats, currency)
        server.wallet.set(stats, amount, currency)
    except WalletError as exc:
        raise CharacterToolError(str(exc)) from None
    await _write(server, character_id, stats=stats)
    await _tell(server, name, "staff.wallet", amount=amount, currency=server.wallet.name(currency))
    return {"name": name, "currency": currency, "before": before, "after": amount}


async def give_item(server: Any, character_id: int, template_id: str) -> dict[str, Any]:
    template = server.content_loader.get_item_template((template_id or "").strip())
    if template is None:
        raise CharacterToolError(f"item_not_found: {template_id}")
    name, _, inventory = await _current(server, character_id)
    entry = {
        "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
        "template": template.id,
        "name": template.name,
        "description": template.description,
        "value": template.value,
    }
    inventory.append(entry)
    await _write(server, character_id, inventory=inventory)
    await _tell(server, name, "staff.item_given", item=template.name)
    return {"name": name, "item": entry}


async def remove_item(server: Any, character_id: int, item_id: str) -> dict[str, Any]:
    name, _, inventory = await _current(server, character_id)
    kept = [it for it in inventory if it.get("id") != item_id]
    if len(kept) == len(inventory):
        raise CharacterToolError(f"item_not_carried: {item_id}")
    removed = next(it for it in inventory if it.get("id") == item_id)
    await _write(server, character_id, inventory=kept)
    await _tell(
        server, name, "staff.item_removed", item=removed.get("name") or removed.get("template")
    )
    return {"name": name, "removed": removed}


async def kick(server: Any, name: str) -> bool:
    """Disconnect the character's session. False when it is not connected."""
    session = _session(server, name)
    if session is None:
        return False
    await _tell(server, name, "staff.kicked")
    await server.session_manager.destroy_session(session.id)
    return True


async def set_suspended(server: Any, account_id: int, reason: str | None) -> dict[str, Any]:
    """Suspend (reason given) or lift a suspension (reason None); suspending disconnects its characters."""
    from datetime import datetime

    from sage.state.models import Account, Character

    async with server.db.session_factory() as session:
        account = await session.get(Account, account_id)
        if account is None:
            raise LookupError("account_not_found")
        if reason is None:
            account.suspended_at, account.suspended_reason = None, None
        else:
            account.suspended_at = datetime.utcnow()
            account.suspended_reason = reason.strip()[:500] or None
        names = [
            c.name
            for c in (
                await session.execute(select(Character).where(Character.account_id == account_id))
            ).scalars()
        ]
        await session.commit()
        suspended = account.suspended_at is not None
    kicked = [n for n in names if suspended and await kick(server, n)]
    return {"account_id": account_id, "suspended": suspended, "disconnected": kicked}


async def sync_live_state(
    server: Any, name: str, *, room_id: str | None, stats: dict | None
) -> None:
    """After a direct Postgres edit of a character, push the same values into its live state."""
    if not await _hot_room(server, name):
        return
    if room_id is not None:
        await _relocate(server, name, room_id)
    if stats is not None:
        await server.redis.set_player_stats(name, stats)
