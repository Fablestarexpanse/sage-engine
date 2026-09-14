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
        "reputation": int(c.reputation),
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
        "echo_credits": int(a.echo_credits),
        "is_gm": bool(a.is_gm),
        "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
        "last_login": a.last_login.isoformat() + "Z" if a.last_login else None,
        "character_count": char_count,
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


async def list_accounts_with_counts(server: Any) -> list[dict[str, Any]]:
    async with server.db.session_factory() as session:
        result = await session.execute(select(Account).order_by(Account.username))
        accounts = list(result.scalars().all())
        out: list[dict[str, Any]] = []
        for a in accounts:
            n = await session.scalar(
                select(func.count()).select_from(Character).where(Character.account_id == a.id)
            )
            out.append(_account_summary_dict(a, int(n or 0)))
        return out


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
        old_ec = int(account.echo_credits)
        old_gm = bool(account.is_gm)
        if patch.get("echo_credits_add") is not None:
            account.echo_credits = max(
                0, int(account.echo_credits) + int(patch["echo_credits_add"])
            )
        elif patch.get("echo_credits") is not None:
            account.echo_credits = max(0, int(patch["echo_credits"]))
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
        new_ec = int(account.echo_credits)
        new_gm = bool(account.is_gm)
        n = await session.scalar(
            select(func.count()).select_from(Character).where(Character.account_id == account_id)
        )
        summary = _account_summary_dict(account, int(n or 0))

    delta = new_ec - old_ec
    c = server.config.comfyui
    lab = (c.currency_display_name or "pixels").strip() or "pixels"

    lines: list[str] = []
    if patch.get("echo_credits_add") is not None or patch.get("echo_credits") is not None:
        if delta > 0:
            lines.append(f"Added {delta} {lab} (balance now {new_ec}).")
        elif delta < 0:
            lines.append(f"Adjusted {lab} by {delta} (balance now {new_ec}).")
        elif patch.get("echo_credits") is not None:
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
            echo_credits=new_ec
            if (patch.get("echo_credits_add") is not None or patch.get("echo_credits") is not None)
            else None,
            echo_credits_added=delta if delta > 0 else None,
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
    async with server.db.session_factory() as session:
        char = await session.get(Character, character_id)
        if char is None or char.account_id != account_id:
            return None
        char_name = char.name
        if "pvp_enabled" in patch:
            char.pvp_enabled = bool(patch["pvp_enabled"])
        if "reputation" in patch:
            char.reputation = int(patch["reputation"])
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

    lines: list[str] = []
    if "reputation" in patch:
        lines.append(f"Character {char_name}: Reputation → {out['reputation']}.")
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
