"""Admin staff accounts: authentication and CRUD (head admin only for writes)."""

from __future__ import annotations

import logging
from typing import Any

import bcrypt
from fastapi import HTTPException
from sqlalchemy import func, select

from sage.state.models import Account, AdminStaff

logger = logging.getLogger(__name__)

VALID_ROLES = frozenset({"head_admin", "admin", "gm"})


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pw_hash.encode("utf-8"))
    except ValueError:
        return False


def staff_public(row: AdminStaff) -> dict[str, Any]:
    perms = row.permissions if isinstance(row.permissions, dict) else {}
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "role": row.role,
        "is_active": row.is_active,
        "permissions": dict(perms),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def find_staff_by_play_username(server: Any, play_username: str) -> AdminStaff | None:
    u = (play_username or "").strip().lower()
    if not u:
        return None
    async with server.db.session_factory() as session:
        r = await session.execute(select(AdminStaff).where(AdminStaff.username == u))
        return r.scalar_one_or_none()


async def set_console_access_for_play_account(
    server: Any,
    account_id: int,
    *,
    password: str,
    role: str,
    permissions: dict[str, Any] | None,
) -> AdminStaff:
    """Create or update admin_staff row whose username matches the play account (lowercased)."""
    async with server.db.session_factory() as session:
        acc = await session.get(Account, account_id)
        if acc is None:
            raise HTTPException(status_code=404, detail="account_not_found")
        u = acc.username.strip().lower()
        display_name = (acc.username or u).strip() or u
        if not u:
            raise HTTPException(status_code=400, detail="invalid_play_username")
    rl = (role or "gm").lower().strip()
    if rl not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")
    perms = permissions if isinstance(permissions, dict) else _default_console_permissions(rl)
    existing = await find_staff_by_play_username(server, u)
    if existing is not None:
        patch: dict[str, Any] = {
            "password": password,
            "role": rl,
            "is_active": True,
            "permissions": perms,
        }
        return await apply_staff_patch(server, existing.id, patch)
    return await create_staff(
        server,
        username=u,
        password=password,
        display_name=display_name,
        role=rl,
        permissions=perms,
    )


def _default_console_permissions(role: str) -> dict[str, Any]:
    if role == "head_admin":
        return {}
    if role == "admin":
        return {
            "tools": [
                "dashboard",
                "forge",
                "operations",
                "players",
                "world",
                "entities",
                "items",
                "glyphs",
                "shops",
                "locations",
                "builder",
                "server",
                "content",
                "settings",
            ],
            "zones": ["*"],
        }
    return {"tools": ["dashboard", "players", "operations"], "zones": ["*"]}


async def revoke_console_access_for_play_account(server: Any, account_id: int) -> bool:
    """Deactivate admin_staff row keyed by same username as play account."""
    async with server.db.session_factory() as session:
        acc = await session.get(Account, account_id)
        if acc is None:
            return False
        u = acc.username.strip().lower()
    st = await find_staff_by_play_username(server, u)
    if st is None or not st.is_active:
        return False
    await apply_staff_patch(server, st.id, {"is_active": False})
    return True


async def authenticate_staff(server: Any, username: str, password: str) -> AdminStaff:
    u = (username or "").strip().lower()
    if not u or not password:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    async with server.db.session_factory() as session:
        r = await session.execute(select(AdminStaff).where(AdminStaff.username == u))
        row = r.scalar_one_or_none()
        if row is None or not row.is_active:
            raise HTTPException(status_code=401, detail="invalid_credentials")
        if not _verify_password(password, row.password_hash):
            raise HTTPException(status_code=401, detail="invalid_credentials")
        return row


async def list_staff(server: Any) -> list[AdminStaff]:
    async with server.db.session_factory() as session:
        r = await session.execute(select(AdminStaff).order_by(AdminStaff.username))
        return list(r.scalars().all())


async def get_staff(server: Any, staff_id: int) -> AdminStaff | None:
    async with server.db.session_factory() as session:
        return await session.get(AdminStaff, staff_id)


async def create_staff(
    server: Any,
    *,
    username: str,
    password: str,
    display_name: str,
    role: str,
    permissions: dict[str, Any] | None,
) -> AdminStaff:
    u = (username or "").strip().lower()
    if not u or not password:
        raise HTTPException(status_code=400, detail="username_and_password_required")
    rl = (role or "gm").lower().strip()
    if rl not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")
    perms = permissions if isinstance(permissions, dict) else {}
    async with server.db.session_factory() as session:
        taken = await session.execute(select(AdminStaff).where(AdminStaff.username == u))
        if taken.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="username_taken")
        row = AdminStaff(
            username=u,
            password_hash=_hash_password(password),
            display_name=(display_name or u).strip() or u,
            role=rl,
            is_active=True,
            permissions=perms,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        logger.info("Created admin staff %s role=%s", u, rl)
        return row


async def apply_staff_patch(server: Any, staff_id: int, patch: dict[str, Any]) -> AdminStaff:
    """Merge partial fields; keys omitted in patch are left unchanged."""
    async with server.db.session_factory() as session:
        row = await session.get(AdminStaff, staff_id)
        if row is None:
            raise HTTPException(status_code=404, detail="staff_not_found")
        if "role" in patch and patch["role"] is not None:
            rl = str(patch["role"]).lower().strip()
            if rl not in VALID_ROLES:
                raise HTTPException(status_code=400, detail="invalid_role")
            if row.role == "head_admin" and rl != "head_admin":
                n = await session.execute(
                    select(func.count())
                    .select_from(AdminStaff)
                    .where(AdminStaff.role == "head_admin", AdminStaff.is_active.is_(True))
                )
                if int(n.scalar() or 0) <= 1:
                    raise HTTPException(status_code=400, detail="cannot_remove_last_head_admin")
            row.role = rl
        if "display_name" in patch and patch["display_name"] is not None:
            row.display_name = str(patch["display_name"]).strip() or row.username
        if "permissions" in patch and patch["permissions"] is not None:
            row.permissions = dict(patch["permissions"])
        if "is_active" in patch:
            is_active = bool(patch["is_active"])
            if not is_active and row.role == "head_admin":
                n = await session.execute(
                    select(func.count())
                    .select_from(AdminStaff)
                    .where(AdminStaff.role == "head_admin", AdminStaff.is_active.is_(True))
                )
                if int(n.scalar() or 0) <= 1:
                    raise HTTPException(status_code=400, detail="cannot_deactivate_last_head_admin")
            row.is_active = is_active
        if "password" in patch and patch["password"] is not None and str(patch["password"]).strip():
            row.password_hash = _hash_password(str(patch["password"]))
        await session.commit()
        await session.refresh(row)
        return row
