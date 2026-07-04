"""Helpers shared by the play services (kept separate to avoid circular imports)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import bcrypt
from sqlalchemy import select

from fablestar.state.models import Account

if TYPE_CHECKING:
    from fablestar.server import FablestarServer


async def authenticate_account(db_session, username: str, password: str) -> Account | None:
    """Fetch the account by username and verify the password. None on failure."""
    result = await db_session.execute(select(Account).where(Account.username == username))
    account = result.scalar_one_or_none()
    if not account or not bcrypt.checkpw(password.encode(), account.password_hash.encode()):
        return None
    return account


async def resolve_play_account(
    db_session,
    server: FablestarServer,
    *,
    token: str = "",
    username: str = "",
    password: str = "",
) -> Account | None:
    """Resolve the account for a /play request: session token first, credentials fallback."""
    tok = (token or "").strip()
    if tok:
        from fablestar.services.play_tokens import decode_play_token

        try:
            account_id = decode_play_token(server, tok)
        except ValueError:
            return None
        return await db_session.get(Account, account_id)
    if not username:
        return None
    return await authenticate_account(db_session, username, password)


def save_portrait_png(png: bytes) -> str:
    """Write a generated portrait PNG under data/portraits and return its /media URL."""
    out_dir = Path("data/portraits")
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.png"
    (out_dir / fname).write_bytes(png)
    return f"/media/portraits/{fname}"
