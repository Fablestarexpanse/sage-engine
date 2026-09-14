"""Admin CRUD helpers for play accounts (players) and their characters."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from sage.state.models import Account, AdminStaff, Character

logger = logging.getLogger(__name__)


def _character_admin_dict(c: Character) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "room_id": c.room_id,
        "portrait_url": c.portrait_url,
        "portrait_prompt": c.portrait_prompt,
        "last_scene_image_url": c.last_scene_image_url,
        "pvp_enabled": bool(c.pvp_enabled),
        "stats": dict(c.stats or {}),
        "inventory": list(c.inventory or []),
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
        "updated_at": c.updated_at.isoformat() + "Z" if c.updated_at else None,
    }


def _account_summary_dict(a: Account, char_count: int) -> dict[str, Any]:
    return {
        "id": a.id,
        "username": a.username,
        "email": a.email,
        "ai_credits": int(a.ai_credits),
        "is_gm": bool(a.is_gm),
        "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
        "last_login": a.last_login.isoformat() + "Z" if a.last_login else None,
        "character_count": char_count,
        "suspended_at": a.suspended_at.isoformat() + "Z" if a.suspended_at else None,
        "suspended_reason": a.suspended_reason,
    }


async def lookup_characters_by_names(server: Any, names: list[str]) -> dict[str, dict[str, int]]:
    """Map character name -> {character_id, account_id} for live-session linking."""
    uniq = sorted({n for n in names if n and isinstance(n, str)})
    if not uniq:
        return {}
    async with server.db.session_factory() as session:
        r = await session.execute(
            select(Character.id, Character.name, Character.account_id).where(
                Character.name.in_(uniq)
            )
        )
        return {
            row.name: {"character_id": int(row.id), "account_id": int(row.account_id)}
            for row in r.all()
        }


ACCOUNT_FILTERS = ("all", "suspended", "gm", "no_characters")
ACCOUNT_SORTS = ("username", "created", "last_login", "characters")


async def search_accounts(
    server: Any,
    *,
    q: str = "",
    filter: str = "all",
    sort: str = "username",
    desc: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """One page of accounts with character counts, filtered and sorted in the database."""
    counts = (
        select(Character.account_id, func.count(Character.id).label("n"))
        .group_by(Character.account_id)
        .subquery()
    )
    n = func.coalesce(counts.c.n, 0)
    stmt = select(Account, n).outerjoin(counts, counts.c.account_id == Account.id)
    needle = (q or "").strip().lower()
    if needle:
        stmt = stmt.where(
            func.lower(Account.username).contains(needle)
            | func.lower(func.coalesce(Account.email, "")).contains(needle)
        )
    if filter == "suspended":
        stmt = stmt.where(Account.suspended_at.is_not(None))
    elif filter == "gm":
        stmt = stmt.where(Account.is_gm.is_(True))
    elif filter == "no_characters":
        stmt = stmt.where(n == 0)
    column = {
        "username": func.lower(Account.username),
        "created": Account.created_at,
        "last_login": Account.last_login,
        "characters": n,
    }.get(sort, func.lower(Account.username))
    order = column.desc().nulls_last() if desc else column.asc().nulls_last()
    async with server.db.session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        result = await session.execute(
            stmt.order_by(order, Account.id).limit(max(1, min(limit, 500))).offset(max(0, offset))
        )
        rows = [_account_summary_dict(a, int(count)) for a, count in result.all()]
    return {"rows": rows, "total": int(total or 0)}


def _console_access_dict(
    account_username: str, staff_row: AdminStaff | None
) -> dict[str, Any] | None:
    if staff_row is None:
        return None
    return {
        "staff_id": staff_row.id,
        "username": staff_row.username,
        "display_name": staff_row.display_name,
        "role": staff_row.role,
        "is_active": bool(staff_row.is_active),
    }


async def get_account_detail(server: Any, account_id: int) -> dict[str, Any] | None:
    async with server.db.session_factory() as session:
        r = await session.execute(
            select(Account)
            .where(Account.id == account_id)
            .options(selectinload(Account.characters))
        )
        account = r.scalar_one_or_none()
        if account is None:
            return None
        chars = sorted(account.characters, key=lambda c: c.id)
        u = account.username.strip().lower()
        st = None
        if u:
            sr = await session.execute(select(AdminStaff).where(AdminStaff.username == u))
            st = sr.scalar_one_or_none()
        return {
            **_account_summary_dict(account, len(chars)),
            "characters": [_character_admin_dict(c) for c in chars],
            "console_access": _console_access_dict(account.username, st),
        }


async def patch_account(
    server: Any,
    account_id: int,
    patch: dict[str, Any],
    *,
    actor: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    async with server.db.session_factory() as session:
        account = await session.get(Account, account_id)
        if account is None:
            return None
        old_ec = int(account.ai_credits)
        old_gm = bool(account.is_gm)
        if patch.get("ai_credits_add") is not None:
            account.ai_credits = max(0, int(account.ai_credits) + int(patch["ai_credits_add"]))
        elif patch.get("ai_credits") is not None:
            account.ai_credits = max(0, int(patch["ai_credits"]))
        if "is_gm" in patch:
            account.is_gm = bool(patch["is_gm"])
        if "email" in patch:
            v = patch["email"]
            if v is None or (isinstance(v, str) and not v.strip()):
                account.email = None
            elif isinstance(v, str):
                account.email = v.strip() or None
        await session.commit()
        await session.refresh(account)
        new_ec = int(account.ai_credits)
        new_gm = bool(account.is_gm)
        n = await session.scalar(
            select(func.count()).select_from(Character).where(Character.account_id == account_id)
        )
        summary = _account_summary_dict(account, int(n or 0))

    delta = new_ec - old_ec
    c = server.config.comfyui
    lab = (c.currency_display_name or "credits").strip() or "credits"

    lines: list[str] = []
    if patch.get("ai_credits_add") is not None or patch.get("ai_credits") is not None:
        if delta > 0:
            lines.append(f"Added {delta} {lab} (balance now {new_ec}).")
        elif delta < 0:
            lines.append(f"Adjusted {lab} by {delta} (balance now {new_ec}).")
        elif patch.get("ai_credits") is not None:
            lines.append(f"{lab.capitalize()} balance set to {new_ec}.")
    if "is_gm" in patch and new_gm != old_gm:
        lines.append(f"In-game GM crown: {'enabled' if new_gm else 'disabled'}.")
    if "email" in patch:
        lines.append("Email updated.")

    if actor and lines:
        await server.notify_play_clients_staff_audit(
            account_id,
            actor_display_name=str(actor.get("display_name") or actor.get("username") or "Staff"),
            actor_role=str(actor.get("role") or "gm"),
            summary_lines=lines,
            ai_credits=new_ec
            if (patch.get("ai_credits_add") is not None or patch.get("ai_credits") is not None)
            else None,
            ai_credits_added=delta if delta > 0 else None,
            play_account_is_gm=new_gm if "is_gm" in patch else None,
        )
    elif delta > 0 and not actor:
        await server.notify_play_clients_echo_grant(account_id, added=delta, new_balance=new_ec)

    return summary


async def patch_character(
    server: Any,
    account_id: int,
    character_id: int,
    patch: dict[str, Any],
    *,
    actor: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from sage.admin.character_tools import snapshot

    async with server.db.session_factory() as session:
        char = await session.get(Character, character_id)
        if char is None or char.account_id != account_id:
            return None
    by = str((actor or {}).get("username") or "")
    await snapshot(server, character_id, "account editor save", by)
    async with server.db.session_factory() as session:
        char = await session.get(Character, character_id)
        char_name = char.name
        if "pvp_enabled" in patch:
            char.pvp_enabled = bool(patch["pvp_enabled"])
        if "room_id" in patch:
            rid = patch["room_id"]
            if isinstance(rid, str) and rid.strip():
                char.room_id = rid.strip()[:255]
        if "portrait_url" in patch:
            pu = patch["portrait_url"]
            char.portrait_url = (pu.strip() or None) if isinstance(pu, str) else None
        if "portrait_prompt" in patch:
            pp = patch["portrait_prompt"]
            char.portrait_prompt = pp if isinstance(pp, str) and pp.strip() else None
        if "stats" in patch and isinstance(patch["stats"], dict):
            from sage.world.progression import PREPARE

            char.stats = server.resolvers.get(PREPARE)(dict(patch["stats"]))
        await session.commit()
        await session.refresh(char)
        out = _character_admin_dict(char)
        new_room = char.room_id if "room_id" in patch else None
        new_stats = dict(char.stats or {}) if "stats" in patch else None

    # A character with live state would have this edit copied back over by the next flush.
    from sage.admin.character_tools import sync_live_state

    await sync_live_state(server, char_name, room_id=new_room, stats=new_stats)

    lines: list[str] = []
    if "room_id" in patch:
        lines.append(f"Character {char_name}: Location (room) updated.")
    if "pvp_enabled" in patch:
        lines.append(f"Character {char_name}: PVP {'on' if out['pvp_enabled'] else 'off'}.")
    if "portrait_url" in patch or "portrait_prompt" in patch:
        lines.append(f"Character {char_name}: Portrait updated.")
    if "stats" in patch:
        lines.append(f"Character {char_name}: Stats / proficiency JSON updated.")

    if actor and lines:
        await server.notify_play_clients_staff_audit(
            account_id,
            actor_display_name=str(actor.get("display_name") or actor.get("username") or "Staff"),
            actor_role=str(actor.get("role") or "gm"),
            summary_lines=lines,
            character_name=char_name,
        )

    return out
