"""Admin audit log: every staff change made through the console is recorded.

`record(server, ctx, action, target, **detail)` never raises: a failed audit write is logged, and
the action it describes has already happened. Actions are short dotted names
(`character.move`, `staff.patch`, `lexicon.set` ...); `target` names what was changed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

MAX_DETAIL_CHARS = 4000


def _clean(detail: dict[str, Any]) -> dict[str, Any]:
    """Drop secrets and trim long values so one row stays small."""
    out: dict[str, Any] = {}
    for key, value in detail.items():
        if "password" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            out[key] = "(changed)" if value else None
            continue
        if isinstance(value, str) and len(value) > MAX_DETAIL_CHARS:
            value = value[:MAX_DETAIL_CHARS] + "…"
        out[key] = value
    return out


async def record(server: Any, ctx: Any, action: str, target: str, **detail: Any) -> None:
    from sage.state.models import AdminAuditLog

    staff_id = getattr(ctx, "staff_id", None)
    username = getattr(ctx, "username", None) or ("auth-disabled" if staff_id is None else "?")
    try:
        async with server.db.session_factory() as session:
            session.add(
                AdminAuditLog(
                    created_at=datetime.utcnow(),
                    staff_id=staff_id,
                    staff_username=str(username)[:64],
                    action=action[:64],
                    target=str(target)[:255],
                    detail=_scrub(detail),
                )
            )
            await session.commit()
    except Exception:
        logger.exception("audit: could not record %s on %s by %s", action, target, username)


async def recent(
    server: Any,
    *,
    limit: int = 100,
    before_id: int | None = None,
    action: str | None = None,
    staff: str | None = None,
    target: str | None = None,
) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from sage.state.models import AdminAuditLog

    query = select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(max(1, min(limit, 500)))
    if before_id is not None:
        query = query.where(AdminAuditLog.id < before_id)
    if action:
        query = query.where(AdminAuditLog.action.startswith(action))
    if staff:
        query = query.where(AdminAuditLog.staff_username == staff)
    if target:
        query = query.where(AdminAuditLog.target.contains(target))
    async with server.db.session_factory() as session:
        rows = (await session.execute(query)).scalars().all()
    return [
        {
            "id": r.id,
            "at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "staff_id": r.staff_id,
            "staff": r.staff_username,
            "action": r.action,
            "target": r.target,
            "detail": r.detail or {},
        }
        for r in rows
    ]


# ---- every other staff write, recorded by middleware -------------------------------------

# POSTs that change nothing (generation, tests, probes) and routes that record their own rows.
NOT_RECORDED = (
    "/admin/auth/login",
    "/admin/dev/login",
    "/admin/characters",
    "/forge/generate",
    "/forge/generate-area-prompt",
    "/forge/generate-content",
    "/forge/room-area-image",
    "/llm/test-completion",
    "/comfyui/test-connection",
    "/admin/agents-llm/test",
)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return _clean({k: _scrub(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_scrub(v) for v in value[:50]]
    return value


def should_record(method: str, path: str) -> bool:
    if method not in ("POST", "PUT", "PATCH", "DELETE"):
        return False
    if path.startswith("/play/") or path.startswith("/ws/"):
        return False
    if path.endswith("/suspend") and path.startswith("/admin/player-accounts/"):
        return False
    return not any(path == p or path.startswith(p + "/") for p in NOT_RECORDED)


class AdminAuditMiddleware:
    """ASGI middleware: after a successful staff write, add an audit row (route, target, body)."""

    def __init__(self, app: Any, server: Any):
        self.app = app
        self.server = server

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not should_record(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        status = {"code": 500}

        async def receive_and_keep():
            message = await receive()
            if message["type"] == "http.request":
                chunks.append(message.get("body", b""))
            return message

        async def send_and_watch(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        await self.app(scope, receive_and_keep, send_and_watch)
        if not 200 <= status["code"] < 300:
            return
        # request.state lives in scope["state"]; the auth middleware set admin_ctx there.
        ctx = (scope.get("state") or {}).get("admin_ctx")
        route = scope.get("route")
        template = getattr(route, "path", scope["path"])
        body: Any = None
        raw = b"".join(chunks)
        if raw:
            import json

            try:
                body = _scrub(json.loads(raw))
            except ValueError:
                body = f"({len(raw)} bytes)"
        await record(
            self.server,
            ctx,
            f"{scope['method']} {template}",
            scope["path"],
            path_params=dict(scope.get("path_params") or {}),
            body=body,
        )
