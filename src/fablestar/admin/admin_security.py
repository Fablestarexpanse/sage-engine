"""Admin console auth: JWT, permission checks (tools / zones), and bypass mode."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from fablestar.core.security import jwt_secret_for_server

if TYPE_CHECKING:
    from fablestar.state.models import AdminStaff

# Sidebar / API permission keys (admin UI should match).
# "team" gates only sidebar visibility in the admin UI; the /admin/staff routes
# it points at are head-admin-only regardless (require_head_admin), so no
# backend require_tool("team") exists by design.
NAV_TOOL_IDS = frozenset(
    {
        "dashboard",
        "forge",
        "operations",
        "players",
        "world",
        "entities",
        "items",
        "glyphs",
        "locations",
        "server",
        "content",
        "settings",
        "team",
        "builder",
        "skills",
        "agents",
    }
)


@dataclass
class AdminContext:
    """Resolved staff member for the current HTTP request."""

    staff_id: int
    username: str
    display_name: str
    role: str
    permissions: dict[str, Any] = field(default_factory=dict)
    bypass_auth: bool = False

    @classmethod
    def bypass(cls) -> AdminContext:
        """When admin_auth_required is false — full access for legacy dev installs."""
        return cls(
            staff_id=0,
            username="dev",
            display_name="Developer",
            role="head_admin",
            permissions={},
            bypass_auth=True,
        )

    @classmethod
    def from_staff(cls, row: AdminStaff) -> AdminContext:
        perms = row.permissions if isinstance(row.permissions, dict) else {}
        return cls(
            staff_id=row.id,
            username=row.username,
            display_name=row.display_name or row.username,
            role=(row.role or "gm").lower().strip(),
            permissions=dict(perms),
            bypass_auth=False,
        )

    def is_head_admin(self) -> bool:
        return self.role == "head_admin"

    def _effective_tools(self) -> set[str] | None:
        """None = all tools allowed."""
        if self.bypass_auth or self.role == "head_admin":
            return None
        raw = self.permissions.get("tools")
        if raw is None:
            return None
        if not isinstance(raw, list):
            return None
        return {str(t).strip() for t in raw if str(t).strip()}

    def may_use_tool(self, tool_id: str) -> bool:
        if self.bypass_auth or self.role == "head_admin":
            return True
        allowed = self._effective_tools()
        if allowed is None:
            return True
        return tool_id in allowed

    def _effective_zones(self) -> set[str] | None:
        """None = all zones. Empty set = no zone writes."""
        if self.bypass_auth or self.role == "head_admin":
            return None
        raw = self.permissions.get("zones")
        if raw is None:
            return None
        if raw == "*":
            return None
        if isinstance(raw, list) and "*" in raw:
            return None
        if isinstance(raw, list):
            return {str(z).strip() for z in raw if str(z).strip()}
        return None

    def may_read_zone(self, zone_id: str) -> bool:
        allowed = self._effective_zones()
        if allowed is None:
            return True
        return zone_id in allowed

    def may_write_zone(self, zone_id: str) -> bool:
        return self.may_read_zone(zone_id)

    def allowed_tool_ids(self) -> list[str]:
        et = self._effective_tools()
        if et is None:
            return sorted(NAV_TOOL_IDS)
        return sorted(et & NAV_TOOL_IDS) if et else []

    def public_dict(self) -> dict[str, Any]:
        et = self._effective_tools()
        return {
            "staff_id": self.staff_id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "permissions": self.permissions,
            "tools_effective": sorted(et) if et is not None else None,
            "allowed_tools": self.allowed_tool_ids(),
        }


def issue_staff_token(server: Any, staff_id: int, ttl_seconds: int = 86400) -> str:
    secret = jwt_secret_for_server(server)
    now = int(time.time())
    payload = {"sub": str(staff_id), "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_staff_token(server: Any, token: str) -> int:
    secret = jwt_secret_for_server(server)
    try:
        data = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise ValueError("invalid_token") from e
    # Play tokens share the signing secret but carry kind="play"; staff ids and
    # play account ids overlap numerically, so cross-use must be rejected.
    if data.get("kind") is not None:
        raise ValueError("invalid_token")
    sub = data.get("sub")
    if sub is None:
        raise ValueError("invalid_token")
    return int(sub)


async def load_admin_context_from_id(server: Any, staff_id: int) -> AdminContext | None:
    from fablestar.state.models import AdminStaff

    async with server.db.session_factory() as session:
        row = await session.get(AdminStaff, staff_id)
        if row is None or not row.is_active:
            return None
        return AdminContext.from_staff(row)


def is_public_admin_path(path: str) -> bool:
    if path in ("/status", "/play/health", "/docs", "/openapi.json", "/redoc"):
        return True
    if path.startswith("/play/"):
        return True
    if path.startswith("/media/portraits/"):
        return True
    if path.startswith("/media/rooms/"):
        return True
    if path.startswith("/media/room-art/"):
        return True
    if path == "/admin/auth/login":
        return True
    if path == "/admin/bootstrap":
        return True
    return False


class NexusAdminAuthMiddleware(BaseHTTPMiddleware):
    """Attach request.state.admin_ctx for protected HTTP routes."""

    def __init__(self, app: Any, server: Any):
        super().__init__(app)
        self.server = server

    async def dispatch(self, request: Request, call_next: Any):
        if is_public_admin_path(request.url.path):
            return await call_next(request)
        cfg = self.server.config.server
        if not cfg.admin_auth_required:
            request.state.admin_ctx = AdminContext.bypass()
            return await call_next(request)
        auth = request.headers.get("Authorization") or ""
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            return JSONResponse({"detail": "not_authenticated"}, status_code=401)
        try:
            sid = decode_staff_token(self.server, token)
        except ValueError:
            return JSONResponse({"detail": "invalid_token"}, status_code=401)
        ctx = await load_admin_context_from_id(self.server, sid)
        if ctx is None:
            return JSONResponse({"detail": "staff_invalid"}, status_code=401)
        request.state.admin_ctx = ctx
        return await call_next(request)


def new_presence_connection_id() -> str:
    return uuid.uuid4().hex
