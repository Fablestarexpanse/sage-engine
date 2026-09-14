"""Staff tools for one player character: find, inspect, move, set money, give or remove items,
restore vitals, kick, and put the character back to an earlier snapshot.

A character's live state lives in Redis once it has logged in since Redis was last cleared (its
location key exists), and the persistence flush copies Redis over Postgres about every minute.
So every write here updates Redis when that state exists, as well as the Postgres row. A write to
Postgres alone would be silently undone by the next flush.

Every change is preceded by a snapshot of the character's room, stats and inventory (who and why),
so staff can undo it. The newest ``SNAPSHOTS_KEPT`` per character are kept.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

SNAPSHOTS_KEPT = 50


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


async def find(
    server: Any,
    query: str = "",
    limit: int = 25,
    *,
    offset: int = 0,
    zone: str = "",
    online: bool | None = None,
) -> dict[str, Any]:
    """One page of characters: name or account contains ``query``, saved room in ``zone``,
    connected or not. Returns {rows, total}."""
    from sage.state.models import Account, Character

    q = (query or "").strip().lower()
    stmt = select(Character, Account).join(Account, Account.id == Character.account_id)
    if q:
        stmt = stmt.where(
            func.lower(Character.name).contains(q) | func.lower(Account.username).contains(q)
        )
    if zone:
        stmt = stmt.where(Character.room_id.startswith(f"{zone}:", autoescape=True))
    if online is not None:
        connected = list(getattr(server.session_manager, "player_to_session", {}) or {})
        stmt = stmt.where(
            Character.name.in_(connected) if online else Character.name.not_in(connected)
        )
    async with server.db.session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await session.execute(
                stmt.order_by(Character.name).limit(max(1, min(limit, 500))).offset(max(0, offset))
            )
        ).all()
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
    return {"rows": out, "total": int(total or 0)}


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
        **await _sheet(server, char.name, stats),
    }


async def _sheet(server: Any, name: str, stats: dict[str, Any]) -> dict[str, Any]:
    """What the player's own panels show: the world's vitals and attributes, and every snapshot
    section with the panel specs plugins declared for it (levels, skills, gear, standings ...)."""
    from sage import lexicon

    def label(key: str, fallback: str) -> str:
        # A world that has not written the label line yet shows the stat key, not "[key]".
        return lexicon.active().get(key) or fallback

    schema = getattr(server.world, "stats", None)
    vitals = [
        {
            "key": v.key,
            "label": label(v.label, v.key),
            "value": stats.get(v.key),
            "max": stats.get(f"max_{v.key}", v.default_max),
        }
        for v in (getattr(schema, "vitals", None) or [])
    ]
    attributes = [
        {"key": a.key, "label": label(a.label, a.key.upper()), "value": stats.get(a.key, a.default)}
        for a in (getattr(schema, "attributes", None) or [])
    ]
    sections: dict[str, Any] = {}
    contributors = getattr(server, "snapshot_contributors", None)
    if contributors is not None:
        try:
            from sage.world.progression import PREPARE

            prepared = server.resolvers.get(PREPARE)(dict(stats))
        except Exception:
            prepared = dict(stats)
        sections = await contributors.build(name, prepared)
    panels = server.panels.specs() if getattr(server, "panels", None) is not None else []
    return {"vitals": vitals, "attributes": attributes, "sections": sections, "panels": panels}


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


async def snapshot(server: Any, character_id: int, reason: str, by: str) -> int:
    """Save the character as it is now (live state when it exists). Returns the snapshot id."""
    from sage.state.models import Character, CharacterSnapshot

    name, stats, inventory = await _current(server, character_id)
    hot = await _hot_room(server, name)
    async with server.db.session_factory() as session:
        char = await session.get(Character, character_id)
        row = CharacterSnapshot(
            character_id=character_id,
            staff_username=(by or "unknown")[:64],
            reason=(reason or "")[:64],
            room_id=hot or (char.room_id if char else ""),
            stats=stats,
            inventory=inventory,
        )
        session.add(row)
        await session.flush()
        stale = (
            await session.execute(
                select(CharacterSnapshot)
                .where(CharacterSnapshot.character_id == character_id)
                .order_by(CharacterSnapshot.id.desc())
                .offset(SNAPSHOTS_KEPT)
            )
        ).scalars()
        for old in list(stale):
            await session.delete(old)
        await session.commit()
        return row.id


async def snapshots(server: Any, character_id: int) -> list[dict[str, Any]]:
    """Every kept snapshot of the character, newest first."""
    from sage.state.models import CharacterSnapshot

    async with server.db.session_factory() as session:
        await _row(session, character_id)
        rows = (
            await session.execute(
                select(CharacterSnapshot)
                .where(CharacterSnapshot.character_id == character_id)
                .order_by(CharacterSnapshot.id.desc())
            )
        ).scalars()
        return [
            {
                "id": r.id,
                "at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "staff": r.staff_username,
                "reason": r.reason,
                "room_id": r.room_id,
                "stats": r.stats,
                "inventory": r.inventory,
            }
            for r in rows
        ]


async def restore_snapshot(server: Any, character_id: int, snapshot_id: int, by: str) -> dict:
    """Put the character back to a snapshot, after taking a snapshot of how it is now."""
    from sage.state.models import CharacterSnapshot

    async with server.db.session_factory() as session:
        row = await session.get(CharacterSnapshot, snapshot_id)
        if row is None or row.character_id != character_id:
            raise LookupError("snapshot_not_found")
        room_id, stats, inventory = row.room_id, dict(row.stats or {}), list(row.inventory or [])
    if server.content_loader.get_room(room_id) is None:
        raise CharacterToolError(f"room_not_found: {room_id}")
    undo = await snapshot(server, character_id, f"restore snapshot #{snapshot_id}", by)
    name = await _write(server, character_id, room_id=room_id, stats=stats, inventory=inventory)
    session = _session(server, name)
    if session is not None:
        await _tell(server, name, "staff.restored_snapshot")
        try:
            await server.dispatcher.dispatch(session, "look")
        except Exception:
            pass
    return {"name": name, "restored": snapshot_id, "undo_snapshot": undo}


async def restore_vitals(server: Any, character_id: int, by: str = "") -> dict[str, Any]:
    """Fill every vital the world declares (hp ...) to its maximum."""
    name, stats, _ = await _current(server, character_id)
    vitals = getattr(getattr(server.world, "stats", None), "vitals", None) or []
    changed = {}
    for vital in vitals:
        top = int(stats.get(f"max_{vital.key}", vital.default_max))
        if stats.get(vital.key) != top:
            changed[vital.key] = {"before": stats.get(vital.key), "after": top}
            stats[vital.key] = top
    if changed:
        await snapshot(server, character_id, "restore vitals", by)
        await _write(server, character_id, stats=stats)
        await _tell(server, name, "staff.restored")
    return {"name": name, "changed": changed}


async def move(server: Any, character_id: int, room_id: str, by: str = "") -> dict[str, Any]:
    room_id = (room_id or "").strip()
    if server.content_loader.get_room(room_id) is None:
        raise CharacterToolError(f"room_not_found: {room_id}")
    await snapshot(server, character_id, f"move to {room_id}", by)
    name = await _write(server, character_id, room_id=room_id)
    session = _session(server, name)
    if session is not None:
        await _tell(server, name, "staff.moved")
        try:
            await server.dispatcher.dispatch(session, "look")
        except Exception:
            pass
    return {"name": name, "room_id": room_id}


async def set_balance(
    server: Any, character_id: int, currency: str, amount: int, by: str = ""
) -> dict[str, Any]:
    from sage.world.wallet import WalletError

    if not isinstance(amount, int) or amount < 0:
        raise CharacterToolError("amount must be a whole number, 0 or more")
    name, stats, _ = await _current(server, character_id)
    try:
        before = server.wallet.balance(stats, currency)
        server.wallet.set(stats, amount, currency)
    except WalletError as exc:
        raise CharacterToolError(str(exc)) from None
    await snapshot(server, character_id, f"set {currency} to {amount}", by)
    await _write(server, character_id, stats=stats)
    await _tell(server, name, "staff.wallet", amount=amount, currency=server.wallet.name(currency))
    return {"name": name, "currency": currency, "before": before, "after": amount}


async def give_item(server: Any, character_id: int, template_id: str, by: str = "") -> dict:
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
    await snapshot(server, character_id, f"give {template.id}", by)
    inventory.append(entry)
    await _write(server, character_id, inventory=inventory)
    await _tell(server, name, "staff.item_given", item=template.name)
    return {"name": name, "item": entry}


async def remove_item(server: Any, character_id: int, item_id: str, by: str = "") -> dict:
    name, _, inventory = await _current(server, character_id)
    kept = [it for it in inventory if it.get("id") != item_id]
    if len(kept) == len(inventory):
        raise CharacterToolError(f"item_not_carried: {item_id}")
    removed = next(it for it in inventory if it.get("id") == item_id)
    await snapshot(server, character_id, f"remove {removed.get('template') or item_id}", by)
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
