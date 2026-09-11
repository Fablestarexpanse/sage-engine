"""Shared FastAPI route dependencies — rate limiter, admin-context extraction, tool guards."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from fablestar.admin.admin_security import NAV_TOOL_IDS, AdminContext

limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded_handler(request: StarletteRequest, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": "too_many_requests"}, status_code=429)


def get_admin_ctx(request: Request) -> AdminContext:
    ctx = getattr(request.state, "admin_ctx", None)
    if ctx is None:
        raise HTTPException(status_code=500, detail="admin_context_missing")
    return ctx


def admin_actor_payload(ctx: AdminContext) -> dict[str, Any] | None:
    if ctx.bypass_auth:
        return None
    return {
        "display_name": ctx.display_name,
        "username": ctx.username,
        "role": ctx.role,
    }


def require_head_or_admin_console(ctx: AdminContext) -> None:
    if ctx.bypass_auth or ctx.is_head_admin() or ctx.role == "admin":
        return
    raise HTTPException(status_code=403, detail="head_or_admin_required")


def assert_console_role_grant_allowed(ctx: AdminContext, target_role: str) -> None:
    tr = (target_role or "gm").lower().strip()
    if tr not in ("gm", "admin", "head_admin"):
        raise HTTPException(status_code=400, detail="invalid_role")
    if ctx.bypass_auth or ctx.is_head_admin():
        return
    if ctx.role == "admin" and tr == "gm":
        return
    raise HTTPException(status_code=403, detail="head_admin_required_for_role")


def require_head_admin(request: Request) -> AdminContext:
    """FastAPI dependency: reject with 403 unless the caller is head admin."""
    ctx = get_admin_ctx(request)
    if not ctx.is_head_admin():
        raise HTTPException(status_code=403, detail="head_admin_only")
    return ctx


def require_tool(tool_id: str):
    if tool_id not in NAV_TOOL_IDS:
        raise ValueError(f"require_tool: unknown tool_id {tool_id!r} — not in NAV_TOOL_IDS")

    def _check_tool_permission(request: Request) -> AdminContext:
        ctx = get_admin_ctx(request)
        if not ctx.may_use_tool(tool_id):
            raise HTTPException(status_code=403, detail=f"tool_denied:{tool_id}")
        return ctx

    return _check_tool_permission


def require_any_tool(*tool_ids: str):
    def _check_any_tool_permission(request: Request) -> AdminContext:
        ctx = get_admin_ctx(request)
        if not any(ctx.may_use_tool(t) for t in tool_ids):
            raise HTTPException(status_code=403, detail="tool_denied")
        return ctx

    return _check_any_tool_permission
