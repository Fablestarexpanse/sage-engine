"""Character tools and the audit log for the admin console.

/admin/characters (find, inspect, move, set money, give or remove items, kick),
/admin/player-accounts/{id}/suspend, and /admin/audit. Every write is recorded in the audit log.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sage.admin import audit, character_tools
from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_any_tool, require_tool

if TYPE_CHECKING:
    from sage.server import SageServer


class MoveBody(BaseModel):
    room_id: str = Field(min_length=3, max_length=255)


class WalletBody(BaseModel):
    currency: str = Field(min_length=1, max_length=64)
    amount: int = Field(ge=0, le=1_000_000_000)


class GiveItemBody(BaseModel):
    template: str = Field(min_length=1, max_length=128)


class SuspendBody(BaseModel):
    reason: str = Field(default="", max_length=500)


def _refuse(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc).strip("'\""))
    return HTTPException(status_code=400, detail=str(exc))


def build_characters_router(server: SageServer) -> APIRouter:
    router = APIRouter()
    # A default value, not a local Annotated alias: postponed annotations cannot see locals.
    players = Depends(require_tool("players"))

    @router.get("/admin/characters")
    async def characters_find(
        _ctx: AdminContext = players,
        q: str = "",
        zone: str = "",
        online: bool | None = None,
        limit: int = Query(default=25, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        """One page of characters: {rows, total}."""
        return await character_tools.find(server, q, limit, offset=offset, zone=zone, online=online)

    @router.get("/admin/characters/{character_id}")
    async def characters_detail(character_id: int, _ctx: AdminContext = players):
        try:
            return await character_tools.detail(server, character_id)
        except LookupError as exc:
            raise _refuse(exc) from None

    @router.post("/admin/characters/{character_id}/move")
    async def characters_move(character_id: int, body: MoveBody, ctx: AdminContext = players):
        zone = body.room_id.split(":", 1)[0]
        if not ctx.may_write_zone(zone):
            raise HTTPException(status_code=403, detail="zone_denied")
        try:
            result = await character_tools.move(server, character_id, body.room_id)
        except (LookupError, ValueError) as exc:
            raise _refuse(exc) from None
        await audit.record(server, ctx, "character.move", result["name"], room_id=body.room_id)
        return result

    @router.post("/admin/characters/{character_id}/wallet")
    async def characters_wallet(character_id: int, body: WalletBody, ctx: AdminContext = players):
        try:
            result = await character_tools.set_balance(
                server, character_id, body.currency, body.amount
            )
        except (LookupError, ValueError) as exc:
            raise _refuse(exc) from None
        await audit.record(
            server, ctx, "character.wallet", result["name"],
            currency=body.currency, before=result["before"], after=result["after"],
        )  # fmt: skip
        return result

    @router.post("/admin/characters/{character_id}/items")
    async def characters_give(character_id: int, body: GiveItemBody, ctx: AdminContext = players):
        try:
            result = await character_tools.give_item(server, character_id, body.template)
        except (LookupError, ValueError) as exc:
            raise _refuse(exc) from None
        await audit.record(
            server, ctx, "character.give_item", result["name"],
            template=body.template, item_id=result["item"]["id"],
        )  # fmt: skip
        return result

    @router.delete("/admin/characters/{character_id}/items/{item_id}")
    async def characters_remove_item(character_id: int, item_id: str, ctx: AdminContext = players):
        try:
            result = await character_tools.remove_item(server, character_id, item_id)
        except (LookupError, ValueError) as exc:
            raise _refuse(exc) from None
        await audit.record(
            server, ctx, "character.remove_item", result["name"],
            item_id=item_id, template=result["removed"].get("template"),
        )  # fmt: skip
        return result

    @router.post("/admin/characters/{character_id}/kick")
    async def characters_kick(character_id: int, ctx: AdminContext = players):
        try:
            info = await character_tools.detail(server, character_id)
        except LookupError as exc:
            raise _refuse(exc) from None
        if not await character_tools.kick(server, info["name"]):
            raise HTTPException(status_code=409, detail="not_connected")
        await audit.record(server, ctx, "character.kick", info["name"])
        return {"name": info["name"], "disconnected": True}

    @router.post("/admin/player-accounts/{account_id}/suspend")
    async def account_suspend(account_id: int, body: SuspendBody, ctx: AdminContext = players):
        try:
            result = await character_tools.set_suspended(server, account_id, body.reason or "")
        except LookupError as exc:
            raise _refuse(exc) from None
        await audit.record(
            server, ctx, "account.suspend", f"account:{account_id}",
            reason=body.reason, disconnected=result["disconnected"],
        )  # fmt: skip
        return result

    @router.delete("/admin/player-accounts/{account_id}/suspend")
    async def account_unsuspend(account_id: int, ctx: AdminContext = players):
        try:
            result = await character_tools.set_suspended(server, account_id, None)
        except LookupError as exc:
            raise _refuse(exc) from None
        await audit.record(server, ctx, "account.unsuspend", f"account:{account_id}")
        return result

    @router.get("/admin/audit")
    async def audit_log(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("team", "operations"))],
        limit: int = 100,
        before: int | None = None,
        action: str = "",
        staff: str = "",
        target: str = "",
    ):
        """Recent staff actions, newest first; `before` pages to older rows."""
        return await audit.recent(
            server, limit=limit, before_id=before,
            action=action or None, staff=staff or None, target=target or None,
        )  # fmt: skip

    return router
