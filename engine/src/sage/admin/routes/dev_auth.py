# DEV-AUTH:FILE — development-only passwordless logins; `python scripts/release_check.py --strip` deletes this file.
"""Passwordless logins for local development (player client and Nexus admin console).

Everything here exists so a developer can test without typing passwords. It is not a release
feature: every piece of it is marked `DEV-AUTH` and `scripts/release_check.py` refuses a release
while any remains (`--strip` removes them).

The routes exist only when `server.dev_mode` and `server.dev_login` are both true at startup, and
each request must come from the machine itself: a loopback connection, and any address a proxy
says it relayed for (X-Forwarded-For, X-Real-IP, Forwarded) loopback too. Otherwise a proxy on this
host (the Vite dev server started with --host, a reverse proxy) would make network clients look
local.

- `GET  /play/dev/status`, `POST /play/dev/login` — a play token for the `dev-login` account; with a
  character name, that character (created if missing) and straight into play; without one, the
  character chooser (to test character creation).
- `GET  /admin/dev/status`, `POST /admin/dev/login` — a staff token for the `dev-staff` head admin.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from sage.admin.admin_security import AdminContext, issue_staff_token
from sage.services.play_tokens import issue_play_token
from sage.services.player_service import reserved_name_reason
from sage.state.models import Account, AdminStaff, Character

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)

DEV_LOGIN_ACCOUNT = "dev-login"
DEV_STAFF_USERNAME = "dev-staff"
LOOPBACK = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"})
_FORWARDED_FOR = re.compile(r"for=\"?\[?([^\]\";,]+)", re.IGNORECASE)

BANNER = (
    "\n"
    + "!" * 72
    + "\nDEV AUTH ENABLED: passwordless player and staff logins for loopback clients.\n"
    "Development only. Set server.dev_login = false on any shared or networked host, and\n"
    "strip it before a release: python scripts/release_check.py --strip\n" + "!" * 72
)


def dev_auth_enabled(server: Any) -> bool:
    cfg = server.config.server
    return bool(getattr(cfg, "dev_mode", False) and getattr(cfg, "dev_login", False))


def _relayed_addresses(request: Request) -> list[str]:
    """Client addresses a proxy says it relayed for (X-Forwarded-For, X-Real-IP, Forwarded)."""
    headers = request.headers
    found = [a.strip() for a in headers.get("x-forwarded-for", "").split(",") if a.strip()]
    found += [a.strip() for a in headers.get("x-real-ip", "").split(",") if a.strip()]
    found += [m.strip() for m in _FORWARDED_FOR.findall(headers.get("forwarded", ""))]
    return found


def request_is_local(request: Request) -> bool:
    """A browser on this machine: a loopback connection, and every relayed address loopback too.

    The dev clients reach Nexus through the Vite proxy, which forwards the browser's address
    (`xfwd`). A proxy that relays for a network client therefore says so and is refused; one that
    claims to relay but names no address (`Forwarded` without `for=`) is refused as well.
    """
    host = (request.client.host if request.client else "") or ""
    if host not in LOOPBACK:
        return False
    relayed = _relayed_addresses(request)
    if not relayed and request.headers.get("forwarded"):
        return False
    return all(address in LOOPBACK for address in relayed)


def _unusable_password() -> str:
    return bcrypt.hashpw(os.urandom(24), bcrypt.gensalt()).decode()


class DevLoginBody(BaseModel):
    # Empty or missing: log in to the dev account without picking a character.
    character: str = Field(default="", max_length=50)


async def player_dev_login(server: SageServer, character_name: str) -> dict[str, Any]:
    """A play token for the dev-login account; with a name, that character (created if missing).

    Characters owned by any other account are refused, so this can't step into a real player.
    """
    player = server.player
    name = " ".join((character_name or "").split())
    if name:
        err, _, _ = player._validate_create_character_inputs(name, "", "")
        if err:
            return err
    async with server.db.session_factory() as db_session:
        found = await db_session.execute(
            select(Account).where(Account.username == DEV_LOGIN_ACCOUNT)
        )
        account = found.scalar_one_or_none()
        if account is None:
            account = Account(
                username=DEV_LOGIN_ACCOUNT,
                password_hash=_unusable_password(),
                last_login=datetime.utcnow(),
                ai_credits=int(server.config.comfyui.starting_ai_credits),
            )
            db_session.add(account)
            await db_session.commit()
            await db_session.refresh(account)

        character = None
        if name:
            row = await db_session.execute(
                select(Character).where(func.lower(Character.name) == name.lower())
            )
            character = row.scalar_one_or_none()
            if character is not None and character.account_id != account.id:
                return {"ok": False, "error": "character_not_dev"}
            if character is None:
                reason = reserved_name_reason(name, player._claimed_names())
                if reason:
                    return {"ok": False, "error": reason}
                character = await player._insert_character(
                    db_session, account.id, name, None, None, None
                )
        account.last_login = datetime.utcnow()
        response = await player.account_characters_response(db_session, account)
        response["play_token"] = issue_play_token(server, account.id)
        if character is not None:
            response["character_id"] = character.id
        await db_session.commit()
    return response


async def staff_dev_login(server: SageServer) -> dict[str, Any]:
    """A staff token for the dev-staff head admin (created if missing, with no usable password)."""
    async with server.db.session_factory() as db_session:
        found = await db_session.execute(
            select(AdminStaff).where(AdminStaff.username == DEV_STAFF_USERNAME)
        )
        row = found.scalar_one_or_none()
        if row is None:
            row = AdminStaff(
                username=DEV_STAFF_USERNAME,
                password_hash=_unusable_password(),
                display_name="Dev staff (passwordless)",
                role="head_admin",
                is_active=True,
                permissions={},
            )
            db_session.add(row)
            await db_session.commit()
            await db_session.refresh(row)
        if not row.is_active:
            return {"ok": False, "error": "dev_staff_disabled"}
        ctx = AdminContext.from_staff(row)
        return {
            "access_token": issue_staff_token(server, row.id),
            "token_type": "bearer",
            "staff": ctx.public_dict(),
        }


def build_dev_auth_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    def allowed(request: Request) -> bool:
        return dev_auth_enabled(server) and request_is_local(request)

    @router.get("/play/dev/status")
    async def play_dev_status(request: Request):
        """Whether passwordless player login is available to this client."""
        return {"enabled": allowed(request)}

    @router.post("/play/dev/login")
    async def play_dev_login(request: Request, body: DevLoginBody):
        """Dev only: a play token for the dev account, optionally as a named character."""
        if not allowed(request):
            raise HTTPException(status_code=404, detail="not_found")
        return await player_dev_login(server, body.character)

    @router.get("/admin/dev/status")
    async def admin_dev_status(request: Request):
        """Whether passwordless staff login is available to this client."""
        return {"enabled": allowed(request)}

    @router.post("/admin/dev/login")
    async def admin_dev_login(request: Request):
        """Dev only: a head-admin staff token without a password."""
        if not allowed(request):
            raise HTTPException(status_code=404, detail="not_found")
        return await staff_dev_login(server)

    return router
