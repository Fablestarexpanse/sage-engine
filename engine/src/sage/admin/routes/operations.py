"""Live operations routes: the staff feed, money in the world, and the scheduled restart."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sage.admin import audit, economy
from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_any_tool, require_tool
from sage.admin.staff_feed import KINDS

if TYPE_CHECKING:
    from sage.server import SageServer


class RestartBody(BaseModel):
    seconds: int = Field(ge=10, le=24 * 3600)
    reason: str = Field(default="", max_length=200)


def build_operations_router(server: SageServer) -> APIRouter:
    router = APIRouter()
    watchers = Depends(require_any_tool("operations", "players"))
    operations = Depends(require_tool("operations"))

    @router.get("/admin/feed")
    async def feed(
        _ctx: AdminContext = watchers,
        after: int = Query(default=0, ge=0),
        kinds: str = "",
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        """Feed entries newer than `after` (an entry id), optionally only some kinds."""
        wanted = {k for k in kinds.split(",") if k in KINDS} or None
        return {"kinds": list(KINDS), "entries": server.staff_feed.since(after, wanted, limit)}

    @router.get("/admin/economy/money")
    async def money(_ctx: AdminContext = watchers):
        """Each currency's total across saved characters and its biggest holders."""
        return await economy.money_overview(server)

    @router.get("/admin/restart")
    async def restart_status(_ctx: AdminContext = watchers):
        return server.restart.status()

    @router.post("/admin/restart")
    async def schedule_restart(body: RestartBody, ctx: AdminContext = operations):
        """Warn players on a countdown, close sign-ins in the last minute, save, and stop."""
        try:
            status = await server.restart.schedule(body.seconds, body.reason, ctx.username)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        await audit.record(
            server,
            ctx,
            "server.restart_scheduled",
            "server",
            seconds=body.seconds,
            reason=body.reason,
        )
        return status

    @router.delete("/admin/restart")
    async def cancel_restart(ctx: AdminContext = operations):
        if not await server.restart.cancel(ctx.username):
            raise HTTPException(status_code=409, detail="no_restart_to_cancel")
        await audit.record(server, ctx, "server.restart_cancelled", "server")
        return server.restart.status()

    return router
