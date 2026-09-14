"""Admin console routes — auth, staff CRUD, player accounts, sessions, status, metrics."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from sage.admin import player_accounts, staff_service
from sage.admin.admin_security import AdminContext, issue_staff_token
from sage.admin.host_metrics import get_host_snapshot
from sage.admin.route_helpers import (
    admin_actor_payload,
    assert_console_role_grant_allowed,
    get_admin_ctx,
    limiter,
    require_any_tool,
    require_head_admin,
    require_head_or_admin_console,
    require_tool,
)

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)


class ServerStatus(BaseModel):
    is_running: bool
    tick_count: int
    active_sessions: int
    uptime_seconds: float


class StaffLoginBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)


class StaffCreateBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    display_name: str = ""
    role: str = "gm"
    permissions: dict[str, Any] = Field(default_factory=dict)


class StaffPatchBody(BaseModel):
    display_name: str | None = None
    role: str | None = None
    permissions: dict[str, Any] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class PlayerAccountPatchBody(BaseModel):
    echo_credits: int | None = None
    echo_credits_add: int | None = None
    is_gm: bool | None = None
    email: str | None = None


class PlayerCharacterPatchBody(BaseModel):
    digi_balance: int | None = None
    pvp_enabled: bool | None = None
    reputation: int | None = None
    room_id: str | None = None
    portrait_url: str | None = None
    portrait_prompt: str | None = None
    stats: dict[str, Any] | None = None


class ConsoleAccessBody(BaseModel):
    """Nexus console login uses the same username as this play account (lowercased)."""

    password: str = Field(..., min_length=8)
    role: str = "gm"


class AdminBroadcastBody(BaseModel):
    message: str


def build_admin_ops_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    @router.get("/admin/bootstrap")
    async def admin_bootstrap():
        return {"admin_auth_required": bool(server.config.server.admin_auth_required)}

    @router.post("/admin/auth/login")
    @limiter.limit("10/minute")
    async def admin_auth_login(request: Request, body: StaffLoginBody):
        row = await staff_service.authenticate_staff(server, body.username, body.password)
        token = issue_staff_token(server, row.id)
        ctx = AdminContext.from_staff(row)
        return {"access_token": token, "token_type": "bearer", "staff": ctx.public_dict()}

    @router.get("/admin/me")
    async def admin_me(request: Request):
        return get_admin_ctx(request).public_dict()

    @router.get("/admin/staff")
    async def admin_staff_list(
        _ctx: Annotated[AdminContext, Depends(require_head_admin)],
    ):
        rows = await staff_service.list_staff(server)
        return [staff_service.staff_public(r) for r in rows]

    @router.post("/admin/staff")
    async def admin_staff_create(
        body: StaffCreateBody,
        _ctx: Annotated[AdminContext, Depends(require_head_admin)],
    ):
        row = await staff_service.create_staff(
            server,
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
            permissions=body.permissions,
        )
        return staff_service.staff_public(row)

    @router.patch("/admin/staff/{staff_id}")
    async def admin_staff_patch(
        staff_id: int,
        body: StaffPatchBody,
        _ctx: Annotated[AdminContext, Depends(require_head_admin)],
    ):
        patch = body.model_dump(exclude_unset=True)
        row = await staff_service.apply_staff_patch(server, staff_id, patch)
        return staff_service.staff_public(row)

    @router.get("/admin/player-accounts")
    async def admin_player_accounts_list(
        _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
    ):
        return await player_accounts.list_accounts_with_counts(server)

    @router.get("/admin/player-accounts/{account_id}")
    async def admin_player_accounts_get(
        account_id: int,
        _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
    ):
        row = await player_accounts.get_account_detail(server, account_id)
        if row is None:
            raise HTTPException(status_code=404, detail="account_not_found")
        return row

    @router.patch("/admin/player-accounts/{account_id}")
    async def admin_player_accounts_patch(
        request: Request,
        account_id: int,
        body: PlayerAccountPatchBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
    ):
        ctx = get_admin_ctx(request)
        patch = body.model_dump(exclude_unset=True)
        row = await player_accounts.patch_account(
            server, account_id, patch, actor=admin_actor_payload(ctx)
        )
        if row is None:
            raise HTTPException(status_code=404, detail="account_not_found")
        return row

    @router.put("/admin/player-accounts/{account_id}/console-access")
    async def admin_player_console_access_put(
        request: Request,
        account_id: int,
        body: ConsoleAccessBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
    ):
        ctx = get_admin_ctx(request)
        require_head_or_admin_console(ctx)
        assert_console_role_grant_allowed(ctx, body.role)
        row = await staff_service.set_console_access_for_play_account(
            server,
            account_id,
            password=body.password,
            role=body.role,
            permissions=None,
        )
        return staff_service.staff_public(row)

    @router.delete("/admin/player-accounts/{account_id}/console-access")
    async def admin_player_console_access_delete(
        request: Request,
        account_id: int,
        _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
    ):
        ctx = get_admin_ctx(request)
        require_head_or_admin_console(ctx)
        ok = await staff_service.revoke_console_access_for_play_account(server, account_id)
        if not ok:
            raise HTTPException(status_code=404, detail="console_access_not_found")
        return {"status": "ok", "revoked": True}

    @router.patch("/admin/player-accounts/{account_id}/characters/{character_id}")
    async def admin_player_character_patch(
        request: Request,
        account_id: int,
        character_id: int,
        body: PlayerCharacterPatchBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
    ):
        ctx = get_admin_ctx(request)
        patch = body.model_dump(exclude_unset=True)
        row = await player_accounts.patch_character(
            server,
            account_id,
            character_id,
            patch,
            actor=admin_actor_payload(ctx),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="character_not_found")
        return row

    @router.get("/status", response_model=ServerStatus)
    async def get_status():
        human_sessions = sum(
            1 for s in server.session_manager.sessions.values() if not getattr(s, "is_agent", False)
        )
        return ServerStatus(
            is_running=server.tick_manager.is_running,
            tick_count=server.tick_manager.tick_count,
            active_sessions=human_sessions,
            uptime_seconds=server.tick_manager.tick_count * server.config.server.tick_rate,
        )

    @router.get("/players")
    async def get_players(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("players", "operations"))],
    ):
        players: list[dict[str, Any]] = []
        redis = server.redis
        for sid, session in server.session_manager.sessions.items():
            # Agents live in the Agents tab, not the player views — keeping
            # them out here is what makes "real player or agent?" answerable.
            if getattr(session, "is_agent", False):
                continue
            room_id = None
            if session.player_id and redis.is_connected:
                try:
                    room_id = await redis.get_player_location(session.player_id)
                except Exception:
                    logger.debug(
                        "get_player_location failed for %s", session.player_id, exc_info=True
                    )
            players.append(
                {
                    "session_id": sid,
                    "player_id": session.player_id,
                    "state": session.state.name,
                    "peer": session.protocol.peer_info,
                    "room_id": room_id,
                }
            )
        names = [p["player_id"] for p in players if p.get("player_id")]
        by_name = await player_accounts.lookup_characters_by_names(server, names)
        for p in players:
            pid = p.get("player_id")
            if pid and pid in by_name:
                p["character_id"] = by_name[pid]["character_id"]
                p["account_id"] = by_name[pid]["account_id"]
        return players

    @router.post("/admin/sessions/{session_id}/disconnect")
    async def admin_disconnect_session(
        session_id: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("operations"))],
    ):
        if session_id not in server.session_manager.sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        await server.session_manager.destroy_session(session_id)
        return {"status": "ok", "session_id": session_id}

    @router.post("/admin/broadcast")
    async def admin_broadcast(
        body: AdminBroadcastBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("operations"))],
    ):
        msg = (body.message or "").strip()
        if not msg:
            raise HTTPException(status_code=400, detail="message is required")
        await server.session_manager.broadcast(f"[Server] {msg}")
        return {"status": "ok", "delivered_hint": "playing sessions"}

    @router.get("/admin/metrics")
    async def admin_metrics(
        _ctx: Annotated[AdminContext, Depends(require_tool("operations"))],
    ):
        """Lightweight process snapshot; command/tick histograms deferred."""
        tm = server.tick_manager
        cfg = server.config.server
        hz = 1.0 / cfg.tick_rate if cfg.tick_rate else 0.0
        return {
            "tick_count": tm.tick_count,
            "tick_rate_hz": hz,
            "active_sessions": sum(
                1
                for s2 in server.session_manager.sessions.values()
                if not getattr(s2, "is_agent", False)
            ),
            "is_running": tm.is_running,
            "uptime_seconds": tm.tick_count * cfg.tick_rate,
            "command_metrics": {
                "note": "Not instrumented yet; hook dispatcher for per-command counts and timing.",
            },
        }

    @router.get("/server/info")
    async def server_info(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("dashboard", "server"))],
    ):
        cfg = server.config
        redis_ok = False
        try:
            if server.redis.is_connected:
                redis_ok = bool(await server.redis.client.ping())
        except Exception:
            redis_ok = False
        db_ok = False
        try:
            async with server.db.session_factory() as session:
                await session.execute(text("SELECT 1"))
                db_ok = True
        except Exception:
            db_ok = False
        llm_probe = await server.llm_client.status_dict(list_timeout=2.0)
        host = await asyncio.to_thread(get_host_snapshot)
        return {
            "tick_rate_hz": 1.0 / cfg.server.tick_rate if cfg.server.tick_rate else 0,
            "tick_interval_s": cfg.server.tick_rate,
            "nexus_port": cfg.server.websocket_port,
            "player_transport": "websocket",
            "max_connections": cfg.server.max_connections,
            "dev_mode": cfg.server.dev_mode,
            "admin_auth_required": cfg.server.admin_auth_required,
            "llm_backend": cfg.llm.primary_backend,
            "llm_url": llm_probe["base_url"],
            "llm_model": cfg.llm.chat_model,
            "llm_detected_model": llm_probe.get("detected_model"),
            "llm_models_align": llm_probe.get("models_align"),
            "llm_chat_model_auto": llm_probe.get("chat_model_auto"),
            "llm_connected": llm_probe["connected"],
            "llm_latency_ms": llm_probe["latency_ms"],
            "sessions": sum(
                1
                for s2 in server.session_manager.sessions.values()
                if not getattr(s2, "is_agent", False)
            ),
            "tick_count": server.tick_manager.tick_count,
            "redis_ok": redis_ok,
            "postgres_ok": db_ok,
            "host": host,
            "last_content_reload_at": server.last_content_reload_at,
        }

    return router
