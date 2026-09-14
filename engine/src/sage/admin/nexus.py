"""NexusApp — FastAPI application shell: middleware, domain routers, and admin WebSockets.

Routes live in domain routers under ``sage.admin.routes`` (play, forge, content,
world, llm_comfyui, admin_ops), each built with the server and included here.

Error-reporting convention
--------------------------
* Admin REST endpoints (/admin/*, /forge/*, /comfyui/*) raise ``HTTPException`` on failure,
  consistent with FastAPI idioms.
* Player WebSocket/REST endpoints (/play/*) return a JSON dict with ``{"ok": False, ...}``
  so the client can distinguish auth failures from transport errors without parsing status codes.
  This split is intentional — admin callers are server-side tools; player callers are browsers.

Play message shapes are documented as TypedDicts in ``sage.network.play_messages``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sage.server import SageServer

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from sage.admin.admin_security import (
    AdminContext,
    NexusAdminAuthMiddleware,
    decode_staff_token,
    load_admin_context_from_id,
    new_presence_connection_id,
)
from sage.admin.route_helpers import (
    get_admin_ctx,
    limiter,
    rate_limit_exceeded_handler,
)
from sage.admin.routes.about import build_about_router
from sage.admin.routes.admin_ops import build_admin_ops_router
from sage.admin.routes.characters import build_characters_router
from sage.admin.routes.content import build_content_router
from sage.admin.routes.forge import build_forge_router
from sage.admin.routes.lexicon import build_lexicon_router
from sage.admin.routes.llm_comfyui import build_llm_comfyui_router
from sage.admin.routes.llm_profiles import build_llm_profiles_router
from sage.admin.routes.play import build_play_router
from sage.admin.routes.search import build_search_router
from sage.admin.routes.world import build_world_router

logger = logging.getLogger(__name__)


class NexusApp:
    """
    FastAPI-based administration server (The Nexus).
    Provides the backend for the World Administration Console.

    Deliberately takes the whole server rather than individual subsystems:
    settings routes replace ``server.config`` live (so a captured config object
    would go stale), content routes write ``server.last_content_reload_at``, and
    the routers collectively span every subsystem. The server→nexus→server
    reference pair is the intended composition — the server owns the app's
    lifecycle; the app exposes the server's API surface.
    """

    def __init__(self, server: SageServer):
        self.server = server
        self.app = FastAPI(title="SAGE Nexus API")
        self._active_sockets: list[WebSocket] = []
        self._admin_ws_sockets: list[WebSocket] = []
        self._admin_presence: dict[str, dict[str, Any]] = {}
        self._presence_lock = asyncio.Lock()
        self._setup_routes()
        self._setup_middleware()

    def _setup_middleware(self):
        # Innermost (added first): runs after the auth middleware has resolved the staff member.
        from sage.admin.audit import AdminAuditMiddleware

        self.app.add_middleware(AdminAuditMiddleware, server=self.server)
        cors_origins = list(self.server.config.server.cors_origins or [])
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.add_middleware(NexusAdminAuthMiddleware, server=self.server)
        self.app.state.limiter = limiter
        self.app.add_middleware(SlowAPIMiddleware)
        self.app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
        # The built player client at / (engine/clients/player-ui/dist), when it has been built.
        from sage.admin import player_client

        player_client.install(self.app, self.server)

    async def _admin_ws_auth(self, websocket: WebSocket) -> AdminContext | None:
        """Authenticate via first-message auth envelope: {"type":"auth","token":"<jwt>"}."""
        cfg = self.server.config.server
        if not cfg.admin_auth_required:
            return AdminContext.bypass()
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        except TimeoutError:
            logger.debug("admin ws auth: no auth envelope within 10s")
            return None
        except Exception as e:
            logger.debug("admin ws auth: receive failed: %s", e)
            return None
        try:
            import json as _json

            msg = _json.loads(raw)
            token = (msg.get("token") or "").strip() if isinstance(msg, dict) else ""
        except Exception as e:
            logger.debug("admin ws auth: invalid auth envelope: %s", e)
            return None
        if not token:
            return None
        try:
            sid = decode_staff_token(self.server, token)
        except ValueError:
            return None
        return await load_admin_context_from_id(self.server, sid)

    async def _presence_snapshot_dict(self) -> dict[str, Any]:
        async with self._presence_lock:
            online = list(self._admin_presence.values())
        online.sort(key=lambda x: (x.get("display_name") or "").lower())
        return {"type": "presence", "online": online}

    async def broadcast_admin_presence(self) -> None:
        payload = await self._presence_snapshot_dict()
        dead: list[WebSocket] = []
        for ws in self._admin_ws_sockets:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.debug("broadcast_admin_presence: dropping dead admin socket: %s", e)
                dead.append(ws)
        for ws in dead:
            if ws in self._admin_ws_sockets:
                self._admin_ws_sockets.remove(ws)

    def _setup_routes(self):
        # Domain routers (see sage.admin.routes)
        self.app.include_router(build_admin_ops_router(self.server))
        self.app.include_router(build_about_router(self.server))
        self.app.include_router(build_characters_router(self.server))
        self.app.include_router(build_search_router(self.server))
        self.app.include_router(build_play_router(self.server))
        self.app.include_router(build_content_router(self.server))
        self.app.include_router(build_world_router(self.server))
        self.app.include_router(build_forge_router(self.server))
        self.app.include_router(build_llm_comfyui_router(self.server))
        self.app.include_router(build_llm_profiles_router(self.server))
        self.app.include_router(build_lexicon_router(self.server))
        # DEV-AUTH:BEGIN — passwordless dev logins; stripped for release (scripts/release_check.py).
        from sage.admin.routes.dev_auth import BANNER, build_dev_auth_router, dev_auth_enabled

        if dev_auth_enabled(self.server):
            logger.warning(BANNER)
            self.app.include_router(build_dev_auth_router(self.server))
        # DEV-AUTH:END

        # Presence + log WebSockets live here — they use NexusApp connection state.

        @self.app.get("/admin/presence")
        async def admin_presence_http(request: Request):
            get_admin_ctx(request)
            async with self._presence_lock:
                online = list(self._admin_presence.values())
            online.sort(key=lambda x: (x.get("display_name") or "").lower())
            return {"online": online}

        @self.app.websocket("/ws/admin")
        async def websocket_admin(websocket: WebSocket):
            await websocket.accept()
            ctx = await self._admin_ws_auth(websocket)
            if ctx is None:
                await websocket.close(code=4401)
                return
            conn_id = new_presence_connection_id()
            entry = {
                "connection_id": conn_id,
                "staff_id": ctx.staff_id,
                "username": ctx.username,
                "display_name": ctx.display_name,
                "role": ctx.role,
                "since": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            async with self._presence_lock:
                self._admin_presence[conn_id] = entry
            self._admin_ws_sockets.append(websocket)
            await self.broadcast_admin_presence()
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                async with self._presence_lock:
                    self._admin_presence.pop(conn_id, None)
                if websocket in self._admin_ws_sockets:
                    self._admin_ws_sockets.remove(websocket)
                await self.broadcast_admin_presence()

        @self.app.websocket("/ws/logs")
        async def websocket_logs(websocket: WebSocket):
            await websocket.accept()
            ctx = await self._admin_ws_auth(websocket)
            if ctx is None:
                await websocket.close(code=4401)
                return
            self._active_sockets.append(websocket)
            try:
                while True:
                    await websocket.receive_text()  # Keep connection alive
            except WebSocketDisconnect:
                pass
            finally:
                if websocket in self._active_sockets:
                    self._active_sockets.remove(websocket)

        portrait_dir = Path("data/portraits")
        portrait_dir.mkdir(parents=True, exist_ok=True)
        self.app.mount(
            "/media/portraits",
            StaticFiles(directory=str(portrait_dir.resolve())),
            name="player_portraits",
        )

        room_art_dir = Path("data/rooms")
        room_art_dir.mkdir(parents=True, exist_ok=True)
        self.app.mount(
            "/media/rooms",
            StaticFiles(directory=str(room_art_dir.resolve())),
            name="room_area_art",
        )

    async def broadcast_log(self, message: str, level: str = "info"):
        """Send a log message to all connected admin consoles."""
        dead: list[WebSocket] = []
        for ws in list(self._active_sockets):
            try:
                await ws.send_json({"type": "log", "level": level, "content": message})
            except Exception as e:
                logger.debug("broadcast_log: dropping dead admin socket: %s", e)
                dead.append(ws)
        for ws in dead:
            if ws in self._active_sockets:
                self._active_sockets.remove(ws)

    async def start(self):
        """Run the uvicorn server in the same event loop."""
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.server.config.server.websocket_port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        handler = AdminLogBroadcastHandler(self, asyncio.get_running_loop())
        logging.getLogger().addHandler(handler)
        try:
            await server.serve()
        finally:
            logging.getLogger().removeHandler(handler)


class AdminLogBroadcastHandler(logging.Handler):
    """Forwards server log records (WARNING and above) to admin consoles on /ws/logs."""

    def __init__(
        self, nexus: NexusApp, loop: asyncio.AbstractEventLoop, level: int = logging.WARNING
    ):
        super().__init__(level)
        self.nexus = nexus
        self.loop = loop
        self.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        # Never feed the socket's own failures back into it.
        if record.name == __name__ or not self.nexus._active_sockets:
            return
        try:
            message = self.format(record).splitlines()[0][:500]
            level = record.levelname.lower()
            coro_factory = lambda: self.nexus.broadcast_log(message, level)  # noqa: E731
            self.loop.call_soon_threadsafe(lambda: self.loop.create_task(coro_factory()))
        except Exception:
            self.handleError(record)
