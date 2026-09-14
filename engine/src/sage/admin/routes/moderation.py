"""Moderation routes for the admin console: settings, address bans, sign-in history, mutes, reports.

Mutes, reports and sign-in history need the players tool. Settings, bans and erasing addresses
need operations. Every write is recorded by the audit middleware.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_tool
from sage.services import moderation

if TYPE_CHECKING:
    from sage.server import SageServer


class SettingsBody(BaseModel):
    registration_open: bool | None = None
    record_login_addresses: bool | None = None
    login_history_days: int | None = Field(default=None, ge=1, le=3650)
    report_cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)


class BanBody(BaseModel):
    network: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=500)
    days: int | None = Field(default=None, ge=1, le=3650)


class MuteBody(BaseModel):
    minutes: int = Field(ge=1, le=60 * 24 * 365)
    reason: str = Field(default="", max_length=500)


class ReportBody(BaseModel):
    status: str | None = None
    staff_note: str | None = Field(default=None, max_length=2000)


def build_moderation_router(server: SageServer) -> APIRouter:
    router = APIRouter()
    players = Depends(require_tool("players"))
    operations = Depends(require_tool("operations"))

    @router.get("/admin/moderation/settings")
    async def get_settings(_ctx: AdminContext = players):
        return moderation.settings(server).model_dump()

    @router.patch("/admin/moderation/settings")
    async def patch_settings(body: SettingsBody, _ctx: AdminContext = operations):
        """Change moderation settings and write config/moderation.toml."""
        try:
            server.update_moderation_settings(body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return moderation.settings(server).model_dump()

    @router.get("/admin/moderation/bans")
    async def list_bans(_ctx: AdminContext = players):
        from sage.state.models import AddressBan

        now = datetime.utcnow()
        async with server.db.session_factory() as session:
            rows = (
                await session.execute(select(AddressBan).order_by(AddressBan.created_at.desc()))
            ).scalars()
            return [
                {
                    "id": b.id,
                    "network": b.network,
                    "reason": b.reason,
                    "created_at": b.created_at.isoformat() + "Z",
                    "created_by": b.created_by,
                    "expires_at": b.expires_at.isoformat() + "Z" if b.expires_at else None,
                    "active": b.expires_at is None or b.expires_at > now,
                }
                for b in rows
            ]

    @router.post("/admin/moderation/bans")
    async def add_ban(body: BanBody, ctx: AdminContext = operations):
        """Refuse an address or range (CIDR) at sign-in, registration and play."""
        from sage.state.models import AddressBan

        try:
            network = moderation.parse_network(body.network)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        expires = datetime.utcnow() + timedelta(days=body.days) if body.days else None
        try:
            async with server.db.session_factory() as session:
                row = AddressBan(
                    network=network,
                    reason=body.reason.strip(),
                    created_by=ctx.username[:64],
                    expires_at=expires,
                )
                session.add(row)
                await session.commit()
                return {"id": row.id, "network": network}
        except IntegrityError:
            raise HTTPException(status_code=409, detail="already_banned") from None

    @router.delete("/admin/moderation/bans/{ban_id}")
    async def remove_ban(ban_id: int, _ctx: AdminContext = operations):
        from sage.state.models import AddressBan

        async with server.db.session_factory() as session:
            row = await session.get(AddressBan, ban_id)
            if row is None:
                raise HTTPException(status_code=404, detail="ban_not_found")
            await session.delete(row)
            await session.commit()
        return {"removed": ban_id}

    @router.get("/admin/moderation/logins")
    async def logins(
        _ctx: AdminContext = players,
        account_id: int | None = None,
        address: str = "",
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        """Sign-ins newest first, by account or by address or range."""
        try:
            return await moderation.login_history(
                server, account_id=account_id, address=address, limit=limit, offset=offset
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/admin/moderation/erase-addresses")
    async def erase_all_addresses(_ctx: AdminContext = operations):
        """Blank every stored sign-in address (the sign-in times stay)."""
        return {"erased": await moderation.erase_addresses(server)}

    @router.delete("/admin/player-accounts/{account_id}/logins")
    async def erase_account_addresses(account_id: int, _ctx: AdminContext = players):
        """Blank one account's stored sign-in addresses, for example when a player asks."""
        return {"erased": await moderation.erase_addresses(server, account_id)}

    @router.post("/admin/player-accounts/{account_id}/mute")
    async def mute(account_id: int, body: MuteBody, _ctx: AdminContext = players):
        try:
            return await moderation.set_mute(server, account_id, body.minutes, body.reason)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from None

    @router.delete("/admin/player-accounts/{account_id}/mute")
    async def unmute(account_id: int, _ctx: AdminContext = players):
        try:
            return await moderation.set_mute(server, account_id, None)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from None

    @router.get("/admin/reports")
    async def list_reports(
        _ctx: AdminContext = players,
        status: str = "open",
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        return await moderation.reports(server, status=status, limit=limit, offset=offset)

    @router.patch("/admin/reports/{report_id}")
    async def patch_report(report_id: int, body: ReportBody, ctx: AdminContext = players):
        try:
            return await moderation.update_report(
                server, report_id, status=body.status, note=body.staff_note, by=ctx.username
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    return router
