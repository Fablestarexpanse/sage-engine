"""Helpers shared by the play services (kept separate to avoid circular imports)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import bcrypt
from sqlalchemy import select

from sage.state.models import Account

if TYPE_CHECKING:
    from sage.server import SageServer


async def authenticate_account(db_session, username: str, password: str) -> Account | None:
    """Fetch the account by username and verify the password. None on failure."""
    result = await db_session.execute(select(Account).where(Account.username == username))
    account = result.scalar_one_or_none()
    if not account or not bcrypt.checkpw(password.encode(), account.password_hash.encode()):
        return None
    return account


async def resolve_play_account_or_error(
    server: SageServer,
    *,
    token: str = "",
    username: str = "",
    password: str = "",
) -> tuple[Account | None, dict | None]:
    """Auth preamble for /play service methods that only need the account itself.

    Opens its own short-lived session; returns (account, None) on success or
    (None, {"ok": False, ...}) ready to return to the caller. Methods that keep
    using the DB session must call resolve_play_account() inside their own
    session instead.
    """
    username = (username or "").strip()
    if not username and not token:
        return None, {"ok": False, "error": "username_required"}
    async with server.db.session_factory() as db_session:
        account = await resolve_play_account(
            db_session, server, token=token, username=username, password=password
        )
    if account is None:
        return None, {"ok": False, "error": "invalid_credentials"}
    return account, None


async def resolve_play_account(
    db_session,
    server: SageServer,
    *,
    token: str = "",
    username: str = "",
    password: str = "",
) -> Account | None:
    """Resolve the account for a /play request: session token first, credentials fallback."""
    tok = (token or "").strip()
    if tok:
        from sage.services.play_tokens import decode_play_token

        try:
            account_id = decode_play_token(server, tok)
        except ValueError:
            return None
        account = await db_session.get(Account, account_id)
    elif username:
        account = await authenticate_account(db_session, username, password)
    else:
        return None
    # A suspended account's tokens and password stop working (staff suspension, admin console).
    if account is not None and getattr(account, "suspended_at", None) is not None:
        return None
    return account


def save_portrait_png(png: bytes) -> str:
    """Write a generated portrait PNG under data/portraits and return its /media URL."""
    out_dir = Path("data/portraits")
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.png"
    (out_dir / fname).write_bytes(png)
    return f"/media/portraits/{fname}"
