"""NexusApp — FastAPI application with all admin REST routes, WebSocket handlers, and middleware."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

import uvicorn
import yaml
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text
from starlette.requests import Request as StarletteRequest
from starlette.responses import FileResponse, JSONResponse

from fablestar.admin import content_browser, player_accounts, staff_service
from fablestar.admin.admin_security import (
    AdminContext,
    NexusAdminAuthMiddleware,
    decode_staff_token,
    issue_staff_token,
    load_admin_context_from_id,
    new_presence_connection_id,
)
from fablestar.admin.host_metrics import get_host_snapshot
from fablestar.admin.world_live import build_world_live_snapshot
from fablestar.network.websocket_protocol import WebSocketProtocol

logger = logging.getLogger(__name__)

_limiter = Limiter(key_func=get_remote_address)


def _rate_limit_exceeded_handler(request: StarletteRequest, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": "too_many_requests"}, status_code=429)


def get_admin_ctx(request: Request) -> AdminContext:
    ctx = getattr(request.state, "admin_ctx", None)
    if ctx is None:
        raise HTTPException(status_code=500, detail="admin_context_missing")
    return ctx


def _admin_actor_payload(ctx: AdminContext) -> dict[str, Any] | None:
    if ctx.bypass_auth:
        return None
    return {
        "display_name": ctx.display_name,
        "username": ctx.username,
        "role": ctx.role,
    }


def _require_head_or_admin_console(ctx: AdminContext) -> None:
    if ctx.bypass_auth or ctx.is_head_admin() or ctx.role == "admin":
        return
    raise HTTPException(status_code=403, detail="head_or_admin_required")


def _assert_console_role_grant_allowed(ctx: AdminContext, target_role: str) -> None:
    tr = (target_role or "gm").lower().strip()
    if tr not in ("gm", "admin", "head_admin"):
        raise HTTPException(status_code=400, detail="invalid_role")
    if ctx.bypass_auth or ctx.is_head_admin():
        return
    if ctx.role == "admin" and tr == "gm":
        return
    raise HTTPException(status_code=403, detail="head_admin_required_for_role")


def require_tool(tool_id: str):
    def _dep(request: Request) -> AdminContext:
        ctx = get_admin_ctx(request)
        if not ctx.may_use_tool(tool_id):
            raise HTTPException(status_code=403, detail=f"tool_denied:{tool_id}")
        return ctx

    return _dep


def require_any_tool(*tool_ids: str):
    def _dep(request: Request) -> AdminContext:
        ctx = get_admin_ctx(request)
        if not any(ctx.may_use_tool(t) for t in tool_ids):
            raise HTTPException(status_code=403, detail="tool_denied")
        return ctx

    return _dep

class ServerStatus(BaseModel):
    is_running: bool
    tick_count: int
    active_sessions: int
    uptime_seconds: float

class PlayAuthBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)


class PlayAuthCharactersBody(BaseModel):
    """Re-list characters; optional delete, scene LLM suggest, or scene Comfy generate (same auth as login)."""

    username: str
    password: str = Field(..., min_length=8)
    delete_character_id: int | None = None
    suggest_scene: bool = False
    narrative_context: str = ""
    room_hint: str = ""
    generate_scene: bool = False
    scene_prompt: str = ""
    character_id: int | None = None


class PlayCreateCharacterBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    name: str
    portrait_prompt: str = ""
    portrait_url: str = ""
    # Optional chargen: leaf_id -> levels, sum <= 15, each <= 5 (see /play/proficiencies/catalog).
    starter_proficiencies: dict[str, Any] | None = None


class PlayDeleteCharacterBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    character_id: int = Field(..., ge=1)


class PlayPortraitBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    appearance_prompt: str = ""


class PlaySuggestPortraitPromptBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    character_name: str = ""
    appearance_notes: str = ""


class PlaySceneSuggestBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    narrative_context: str = ""
    room_hint: str = ""


class PlaySceneGenerateBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    scene_prompt: str = ""
    character_id: int | None = None


class PlaySceneGalleryListBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)


class PlaySceneApplyGalleryBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    gallery_id: int = Field(..., ge=1)
    character_id: int = Field(..., ge=1)


class ForgeRequest(BaseModel):
    seed: str
    room_type: str = "chamber"
    depth: int = 1

class ForgeInjection(BaseModel):
    id: str
    yaml_content: str

class ForgeGenericRequest(BaseModel):
    category: str
    seed: str
    context: dict[str, Any] = {}


class ForgeAreaImagePromptRequest(BaseModel):
    room_name: str = ""
    room_type: str = "chamber"
    depth: int = 1
    description_base: str = ""


class ForgeRoomAreaImageRequest(BaseModel):
    prompt: str = ""
    # When both set (zone editor), PNG is written next to room YAML for export/import with world content.
    zone_id: str = ""
    room_slug: str = ""

class ContentInjectBody(BaseModel):
    """Write arbitrary YAML content to a file under content/world/."""
    path: str       # e.g. "entities/stalker" or "items/sword"
    yaml_content: str

class SpawnRequest(BaseModel):
    template: str   # entity template ID to spawn


class AdminBroadcastBody(BaseModel):
    message: str


class LLMSettingsBody(BaseModel):
    primary_backend: str | None = None
    lm_studio_url: str | None = None
    lm_studio_key: str | None = None
    ollama_url: str | None = None
    timeout_seconds: float | None = None
    chat_model: str | None = None
    temperature: float | None = None
    cache_ttl: int | None = None


class ComfyUISettingsBody(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    workflow_path: str | None = None
    positive_prompt_node_id: str | None = None
    output_node_id: str | None = None
    area_workflow_path: str | None = None
    area_positive_prompt_node_id: str | None = None
    area_output_node_id: str | None = None
    checkpoint_name: str | None = None
    timeout_seconds: float | None = None
    poll_interval_seconds: float | None = None
    economy_enabled: bool | None = None
    starting_echo_credits: int | None = None
    portrait_generation_cost: int | None = None
    area_generation_cost: int | None = None
    character_create_portrait_cost: int | None = None
    currency_display_name: str | None = None
    pixels_per_usd: int | None = None


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


class RoomJsonBody(BaseModel):
    """Full or partial room document merged into existing YAML."""

    room: dict[str, Any] = Field(default_factory=dict)


class CreateRoomBody(BaseModel):
    slug: str
    room: dict[str, Any] = Field(default_factory=dict)


class CreateZoneBody(BaseModel):
    id: str
    name: str = ""


class ZonePositionsBody(BaseModel):
    positions: dict[str, dict[str, float]] = Field(default_factory=dict)


class CreateSystemBody(BaseModel):
    id: str
    name: str = ""
    x: float = 0
    y: float = 0
    z: float = 0
    faction: str = "neutral"
    security: str = "low"
    star_type: str = "G2V"
    star_name: str = ""
    add_to_galaxy: bool = True


class SystemDocumentBody(BaseModel):
    """Full YAML root, e.g. {\"system\": {...}}."""

    document: dict[str, Any]


class CreateShipBody(BaseModel):
    id: str
    name: str = ""
    size: str = "small"


def _llm_public_config(cfg) -> dict[str, Any]:
    llm = cfg.llm
    key = llm.lm_studio_key or ""
    return {
        "primary_backend": llm.primary_backend,
        "lm_studio_url": llm.lm_studio_url,
        "lm_studio_key_set": bool(key and key != "not-needed"),
        "ollama_url": llm.ollama_url,
        "timeout_seconds": llm.timeout_seconds,
        "chat_model": llm.chat_model,
        "temperature": llm.temperature,
        "cache_ttl": llm.cache_ttl,
    }


class NexusApp:
    """
    FastAPI-based administration server (The Nexus).
    Provides the backend for the World Administration Console.
    """
    def __init__(self, server: FablestarServer):
        self.server = server
        self.app = FastAPI(title="Fablestar Nexus API")
        self._active_sockets: list[WebSocket] = []
        self._admin_ws_sockets: list[WebSocket] = []
        self._admin_presence: dict[str, dict[str, Any]] = {}
        self._presence_lock = asyncio.Lock()
        self._setup_routes()
        self._setup_middleware()

    def _setup_middleware(self):
        cors_origins = list(self.server.config.server.cors_origins or [])
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.add_middleware(NexusAdminAuthMiddleware, server=self.server)
        self.app.state.limiter = _limiter
        self.app.add_middleware(SlowAPIMiddleware)
        self.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    async def _admin_ws_auth(self, websocket: WebSocket) -> AdminContext | None:
        """Authenticate via first-message auth envelope: {"type":"auth","token":"<jwt>"}."""
        cfg = self.server.config.server
        if not cfg.admin_auth_required:
            return AdminContext.bypass()
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        except TimeoutError:
            return None
        except Exception:
            return None
        try:
            import json as _json
            msg = _json.loads(raw)
            token = (msg.get("token") or "").strip() if isinstance(msg, dict) else ""
        except Exception:
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
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._admin_ws_sockets:
                self._admin_ws_sockets.remove(ws)

    def _setup_routes(self):
        @self.app.get("/admin/bootstrap")
        async def admin_bootstrap():
            return {"admin_auth_required": bool(self.server.config.server.admin_auth_required)}

        @self.app.post("/admin/auth/login")
        @_limiter.limit("10/minute")
        async def admin_auth_login(request: Request, body: StaffLoginBody):
            row = await staff_service.authenticate_staff(self.server, body.username, body.password)
            token = issue_staff_token(self.server, row.id)
            ctx = AdminContext.from_staff(row)
            return {"access_token": token, "token_type": "bearer", "staff": ctx.public_dict()}

        @self.app.get("/admin/me")
        async def admin_me(request: Request):
            return get_admin_ctx(request).public_dict()

        @self.app.get("/admin/presence")
        async def admin_presence_http(request: Request):
            get_admin_ctx(request)
            async with self._presence_lock:
                online = list(self._admin_presence.values())
            online.sort(key=lambda x: (x.get("display_name") or "").lower())
            return {"online": online}

        @self.app.get("/admin/staff")
        async def admin_staff_list(request: Request):
            ctx = get_admin_ctx(request)
            if not ctx.is_head_admin():
                raise HTTPException(status_code=403, detail="head_admin_only")
            rows = await staff_service.list_staff(self.server)
            return [staff_service.staff_public(r) for r in rows]

        @self.app.post("/admin/staff")
        async def admin_staff_create(request: Request, body: StaffCreateBody):
            ctx = get_admin_ctx(request)
            if not ctx.is_head_admin():
                raise HTTPException(status_code=403, detail="head_admin_only")
            row = await staff_service.create_staff(
                self.server,
                username=body.username,
                password=body.password,
                display_name=body.display_name,
                role=body.role,
                permissions=body.permissions,
            )
            return staff_service.staff_public(row)

        @self.app.patch("/admin/staff/{staff_id}")
        async def admin_staff_patch(request: Request, staff_id: int, body: StaffPatchBody):
            ctx = get_admin_ctx(request)
            if not ctx.is_head_admin():
                raise HTTPException(status_code=403, detail="head_admin_only")
            patch = body.model_dump(exclude_unset=True)
            row = await staff_service.apply_staff_patch(self.server, staff_id, patch)
            return staff_service.staff_public(row)

        @self.app.get("/admin/player-accounts")
        async def admin_player_accounts_list(
            _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
        ):
            return await player_accounts.list_accounts_with_counts(self.server)

        @self.app.get("/admin/player-accounts/{account_id}")
        async def admin_player_accounts_get(
            account_id: int,
            _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
        ):
            row = await player_accounts.get_account_detail(self.server, account_id)
            if row is None:
                raise HTTPException(status_code=404, detail="account_not_found")
            return row

        @self.app.patch("/admin/player-accounts/{account_id}")
        async def admin_player_accounts_patch(
            request: Request,
            account_id: int,
            body: PlayerAccountPatchBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
        ):
            ctx = get_admin_ctx(request)
            patch = body.model_dump(exclude_unset=True)
            row = await player_accounts.patch_account(
                self.server, account_id, patch, actor=_admin_actor_payload(ctx)
            )
            if row is None:
                raise HTTPException(status_code=404, detail="account_not_found")
            return row

        @self.app.put("/admin/player-accounts/{account_id}/console-access")
        async def admin_player_console_access_put(
            request: Request,
            account_id: int,
            body: ConsoleAccessBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
        ):
            ctx = get_admin_ctx(request)
            _require_head_or_admin_console(ctx)
            _assert_console_role_grant_allowed(ctx, body.role)
            row = await staff_service.set_console_access_for_play_account(
                self.server,
                account_id,
                password=body.password,
                role=body.role,
                permissions=None,
            )
            return staff_service.staff_public(row)

        @self.app.delete("/admin/player-accounts/{account_id}/console-access")
        async def admin_player_console_access_delete(
            request: Request,
            account_id: int,
            _ctx: Annotated[AdminContext, Depends(require_tool("players"))],
        ):
            ctx = get_admin_ctx(request)
            _require_head_or_admin_console(ctx)
            ok = await staff_service.revoke_console_access_for_play_account(self.server, account_id)
            if not ok:
                raise HTTPException(status_code=404, detail="console_access_not_found")
            return {"status": "ok", "revoked": True}

        @self.app.patch("/admin/player-accounts/{account_id}/characters/{character_id}")
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
                self.server,
                account_id,
                character_id,
                patch,
                actor=_admin_actor_payload(ctx),
            )
            if row is None:
                raise HTTPException(status_code=404, detail="character_not_found")
            return row

        @self.app.get("/status", response_model=ServerStatus)
        async def get_status():
            return ServerStatus(
                is_running=self.server.tick_manager.is_running,
                tick_count=self.server.tick_manager.tick_count,
                active_sessions=len(self.server.session_manager.sessions),
                uptime_seconds=self.server.tick_manager.tick_count * self.server.config.server.tick_rate
            )

        @self.app.get("/play/health")
        async def play_health():
            """Cheap check that player REST routes are live (no DB)."""
            return {"ok": True, "play_api": "v1", "proficiency_catalog": True}

        @self.app.get("/media/room-art/{zone_id}/{room_slug}/v/{filename}")
        async def media_room_art_variant(zone_id: str, room_slug: str, filename: str):
            """Scene art variant: zones/{zone}/rooms/art/{room}/{filename}.png"""
            seg_re = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
            fn_re = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,120}\.png$")
            if not seg_re.match(zone_id) or not seg_re.match(room_slug) or not fn_re.match(filename):
                raise HTTPException(status_code=404, detail="not_found")
            path = (
                Path("content/world/zones") / zone_id / "rooms" / "art" / room_slug / filename
            ).resolve()
            zones_root = Path("content/world/zones").resolve()
            try:
                path.relative_to(zones_root)
            except ValueError:
                raise HTTPException(status_code=404, detail="not_found") from None
            if not path.is_file():
                raise HTTPException(status_code=404, detail="not_found")
            return FileResponse(path, media_type="image/png")

        @self.app.get("/media/room-art/{zone_id}/{slug}.png")
        async def media_room_art_png(zone_id: str, slug: str):
            """Legacy flat file: zones/{zone}/rooms/art/{slug}.png (bundled with zone)."""
            seg_re = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
            if not seg_re.match(zone_id) or not seg_re.match(slug):
                raise HTTPException(status_code=404, detail="not_found")
            path = (Path("content/world/zones") / zone_id / "rooms" / "art" / f"{slug}.png").resolve()
            zones_root = Path("content/world/zones").resolve()
            try:
                path.relative_to(zones_root)
            except ValueError:
                raise HTTPException(status_code=404, detail="not_found") from None
            if not path.is_file():
                raise HTTPException(status_code=404, detail="not_found")
            return FileResponse(path, media_type="image/png")

        @self.app.post("/play/auth/login")
        @_limiter.limit("10/minute")
        async def play_auth_login(request: Request, body: PlayAuthBody):
            """Web player: validate credentials and list characters."""
            return await self.server.play_login(body.username, body.password)

        @self.app.post("/play/auth/register")
        @_limiter.limit("5/minute")
        async def play_auth_register(request: Request, body: PlayAuthBody):
            """Web player: create account (add characters in the UI)."""
            return await self.server.play_register(body.username, body.password)

        @self.app.post("/play/auth/characters")
        async def play_auth_characters(body: PlayAuthCharactersBody):
            """Re-list characters, or scene suggest/generate/delete when those flags/ids are set."""
            if body.suggest_scene:
                return await self.server.play_suggest_scene_prompt(
                    body.username,
                    body.password,
                    narrative_context=body.narrative_context,
                    room_hint=body.room_hint,
                )
            if body.generate_scene:
                return await self.server.play_generate_scene_image(
                    body.username,
                    body.password,
                    body.scene_prompt,
                    character_id=body.character_id,
                )
            if body.delete_character_id is not None:
                if body.delete_character_id < 1:
                    return {"ok": False, "error": "character_id_invalid"}
                return await self.server.play_delete_character(
                    body.username, body.password, body.delete_character_id
                )
            return await self.server.play_refresh_characters(body.username, body.password)

        @self.app.get("/play/comfyui/status")
        async def play_comfyui_status():
            """Whether ComfyUI portrait generation is configured."""
            return await self.server.play_comfyui_status()

        @self.app.post("/play/characters/portrait")
        async def play_character_portrait(body: PlayPortraitBody):
            """Generate a portrait via ComfyUI (optional); returns /media/portraits/... URL."""
            return await self.server.play_generate_portrait(
                body.username, body.password, body.appearance_prompt
            )

        @self.app.post("/play/characters/suggest-portrait-prompt")
        async def play_suggest_portrait_prompt(body: PlaySuggestPortraitPromptBody):
            """LLM: suggest a ComfyUI portrait prompt from character name and notes."""
            return await self.server.play_suggest_portrait_prompt(
                body.username,
                body.password,
                body.character_name,
                appearance_notes=body.appearance_notes,
            )

        @self.app.post("/play/characters/create")
        async def play_character_create(body: PlayCreateCharacterBody):
            """Create a new character for the account."""
            starter = body.starter_proficiencies
            if isinstance(starter, dict):
                coerced: dict[str, Any] = {str(k): v for k, v in starter.items()}
            else:
                coerced = {}
            return await self.server.play_create_character(
                body.username,
                body.password,
                body.name,
                portrait_prompt=body.portrait_prompt,
                portrait_url=body.portrait_url,
                starter_proficiencies=coerced if coerced else None,
            )

        @self.app.get("/play/proficiencies/catalog")
        async def play_proficiencies_catalog():
            """Public read-only leaf list for chargen skill picker."""
            from fablestar.proficiencies.starter import (
                STARTER_MAX_PER_LEAF,
                STARTER_POINTS_BUDGET,
                catalog_leaves_for_client,
            )

            reg = self.server.content_loader.get_proficiency_registry()
            leaves = catalog_leaves_for_client(reg)
            domains = sorted({x["domain"] for x in leaves})
            return {
                "budget": STARTER_POINTS_BUDGET,
                "max_per_leaf": STARTER_MAX_PER_LEAF,
                "domains": domains,
                "leaves": leaves,
            }

        @self.app.post("/play/characters/delete")
        async def play_character_delete(body: PlayDeleteCharacterBody):
            """Remove a character owned by the account."""
            return await self.server.play_delete_character(
                body.username, body.password, body.character_id
            )

        @self.app.post("/play/scene/suggest-prompt")
        async def play_scene_suggest_prompt(body: PlaySceneSuggestBody):
            """LLM: suggest a ComfyUI environment prompt from recent narrative text."""
            return await self.server.play_suggest_scene_prompt(
                body.username,
                body.password,
                narrative_context=body.narrative_context,
                room_hint=body.room_hint,
            )

        @self.app.post("/play/scene/generate")
        async def play_scene_generate(body: PlaySceneGenerateBody):
            """Run area ComfyUI workflow; returns scene_image_url under /media/rooms/."""
            return await self.server.play_generate_scene_image(
                body.username,
                body.password,
                body.scene_prompt,
                character_id=body.character_id,
            )

        @self.app.post("/play/scene/gallery")
        async def play_scene_gallery(body: PlaySceneGalleryListBody):
            """List scene images saved for this account (ComfyUI history)."""
            return await self.server.play_list_scene_gallery(body.username, body.password)

        @self.app.post("/play/scene/apply-gallery")
        async def play_scene_apply_gallery(body: PlaySceneApplyGalleryBody):
            """Apply a gallery image as this character's current scene art."""
            return await self.server.play_apply_scene_from_gallery(
                body.username,
                body.password,
                body.gallery_id,
                body.character_id,
            )

        @self.app.get("/players")
        async def get_players(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("players", "operations"))],
        ):
            players = []
            redis = self.server.redis
            for sid, session in self.server.session_manager.sessions.items():
                room_id = None
                if session.player_id and redis.client:
                    try:
                        room_id = await redis.get_player_location(session.player_id)
                    except Exception:
                        logger.debug(
                            "get_player_location failed for %s", session.player_id, exc_info=True
                        )
                players.append({
                    "session_id": sid,
                    "player_id": session.player_id,
                    "state": session.state.name,
                    "peer": session.protocol.peer_info,
                    "room_id": room_id,
                })
            names = [p["player_id"] for p in players if p.get("player_id")]
            by_name = await player_accounts.lookup_characters_by_names(self.server, names)
            for p in players:
                pid = p.get("player_id")
                if pid and pid in by_name:
                    p["character_id"] = by_name[pid]["character_id"]
                    p["account_id"] = by_name[pid]["account_id"]
            return players

        @self.app.post("/admin/sessions/{session_id}/disconnect")
        async def admin_disconnect_session(
            session_id: str,
            _ctx: Annotated[AdminContext, Depends(require_tool("operations"))],
        ):
            if session_id not in self.server.session_manager.sessions:
                raise HTTPException(status_code=404, detail="Session not found")
            await self.server.session_manager.destroy_session(session_id)
            return {"status": "ok", "session_id": session_id}

        @self.app.post("/admin/broadcast")
        async def admin_broadcast(
            body: AdminBroadcastBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("operations"))],
        ):
            msg = (body.message or "").strip()
            if not msg:
                raise HTTPException(status_code=400, detail="message is required")
            await self.server.session_manager.broadcast(f"[Server] {msg}")
            return {"status": "ok", "delivered_hint": "playing sessions"}

        @self.app.get("/world/live")
        async def world_live(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("operations", "world"))],
        ):
            if not self.server.redis.client:
                return await build_world_live_snapshot(None)
            return await build_world_live_snapshot(self.server.redis.client)

        @self.app.get("/admin/metrics")
        async def admin_metrics(
            _ctx: Annotated[AdminContext, Depends(require_tool("operations"))],
        ):
            """Lightweight process snapshot; command/tick histograms deferred."""
            tm = self.server.tick_manager
            cfg = self.server.config.server
            hz = 1.0 / cfg.tick_rate if cfg.tick_rate else 0.0
            return {
                "tick_count": tm.tick_count,
                "tick_rate_hz": hz,
                "active_sessions": len(self.server.session_manager.sessions),
                "is_running": tm.is_running,
                "uptime_seconds": tm.tick_count * cfg.tick_rate,
                "command_metrics": {
                    "note": "Not instrumented yet; hook dispatcher for per-command counts and timing.",
                },
            }

        @self.app.get("/content/overview")
        async def content_overview(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("world", "content", "dashboard"))],
        ):
            return content_browser.content_overview()

        @self.app.get("/content/zones")
        async def content_zones(
            _ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        ):
            return content_browser.list_zones()

        @self.app.post("/content/zones")
        async def content_create_zone(
            body: CreateZoneBody,
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            zid = (body.id or "").strip()
            try:
                rooms_path = content_browser.create_zone(zid, body.name or "")
            except FileExistsError:
                raise HTTPException(status_code=409, detail="zone_exists") from None
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.clear_cache()
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "created", "id": zid, "path": str(rooms_path)}

        @self.app.get("/content/zones/{zone_id}/rooms")
        async def content_zone_rooms(
            zone_id: str,
            ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        ):
            if not ctx.may_read_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            rows = content_browser.list_rooms(zone_id)
            if not rows and zone_id not in content_browser.list_zone_ids():
                raise HTTPException(status_code=404, detail="Zone not found")
            return rows

        @self.app.get("/content/entities/spawns")
        async def content_entity_spawns(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "entities", "world"))],
        ):
            return content_browser.aggregate_entity_spawns()

        @self.app.get("/content/items")
        async def content_items(
            _ctx: Annotated[AdminContext, Depends(require_tool("items"))],
        ):
            return content_browser.list_items()

        @self.app.get("/content/glyphs")
        async def content_glyphs(
            _ctx: Annotated[AdminContext, Depends(require_tool("glyphs"))],
        ):
            return content_browser.list_glyphs()

        @self.app.get("/content/proficiencies/catalog")
        async def content_proficiencies_catalog_get(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("content", "skills"))],
        ):
            try:
                return content_browser.read_proficiency_catalog_document()
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="proficiency_catalog_missing")

        @self.app.put("/content/proficiencies/catalog")
        async def content_proficiencies_catalog_put(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("content", "skills"))],
            body: dict[str, Any] = Body(...),
        ):
            try:
                out = content_browser.write_proficiency_catalog_document(body)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.invalidate(Path("content/proficiencies/catalog.json").resolve())
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return out

        @self.app.get("/content/room/{zone_id}/{room_slug}/yaml")
        async def content_room_yaml(
            zone_id: str,
            room_slug: str,
            ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations"))],
        ):
            if not ctx.may_read_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            raw = content_browser.get_room_yaml(zone_id, room_slug)
            if raw is None:
                raise HTTPException(status_code=404, detail="Room not found")
            return {"yaml": raw}

        @self.app.post("/content/cache/reload")
        async def content_cache_reload(
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        ):
            self.server.content_loader.clear_cache()
            self.server.prompt_manager.reload()
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "ok", "message": "Content and prompt caches cleared."}

        @self.app.get("/server/info")
        async def server_info(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("dashboard", "server"))],
        ):
            cfg = self.server.config
            redis_ok = False
            try:
                if self.server.redis.client:
                    redis_ok = bool(await self.server.redis.client.ping())
            except Exception:
                redis_ok = False
            db_ok = False
            try:
                async with self.server.db.session_factory() as session:
                    await session.execute(text("SELECT 1"))
                    db_ok = True
            except Exception:
                db_ok = False
            llm_probe = await self.server.llm_client.status_dict(list_timeout=2.0)
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
                "sessions": len(self.server.session_manager.sessions),
                "tick_count": self.server.tick_manager.tick_count,
                "redis_ok": redis_ok,
                "postgres_ok": db_ok,
                "host": host,
                "last_content_reload_at": self.server.last_content_reload_at,
            }

        @self.app.get("/llm/config")
        async def llm_config(
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        ):
            return _llm_public_config(self.server.config)

        async def _compose_llm_status(*, refresh: bool) -> dict[str, Any]:
            snap = _llm_public_config(self.server.config)
            probe = await self.server.llm_client.status_dict(bypass_cache=refresh)
            snap.update(
                {
                    "connected": probe["connected"],
                    "latency_ms": probe["latency_ms"],
                    "error": probe["error"],
                    "models": probe["models"],
                    "model_count": probe["model_count"],
                    "model_known": probe["model_known"],
                    "base_url": probe["base_url"],
                    "detected_model": probe.get("detected_model"),
                    "detected_model_source": probe.get("detected_model_source"),
                    "models_align": probe.get("models_align"),
                    "chat_model_auto": probe.get("chat_model_auto"),
                    "status_cached": probe.get("cached", False),
                }
            )
            return snap

        @self.app.get("/llm/status")
        async def llm_status(
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
            refresh: bool = Query(default=False),
        ):
            return await _compose_llm_status(refresh=refresh)

        @self.app.patch("/llm/settings")
        async def llm_settings_patch(
            body: LLMSettingsBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
            persist: bool = Query(default=True),
        ):
            patch = body.model_dump(exclude_none=True)
            try:
                self.server.update_llm_settings(patch, persist=persist)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return await _compose_llm_status(refresh=True)

        @self.app.post("/llm/test-completion")
        async def llm_test_completion(
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        ):
            """Minimal chat completion to verify the pipeline (Forge / look use the same client)."""
            eff = await self.server.llm_client.effective_chat_model()
            text = await self.server.llm_client.generate(
                'Reply with exactly one word: "pong"',
                system_prompt="You follow instructions literally.",
                max_tokens=16,
            )
            return {
                "reply": text.strip(),
                "model": eff,
                "chat_model_config": self.server.config.llm.chat_model,
            }

        # ── ComfyUI settings ───────────────────────────────────────────────

        @self.app.get("/comfyui/status")
        async def comfyui_status(
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        ):
            """Full ComfyUI config + live reachability check."""
            return await self.server.play_comfyui_status()

        @self.app.patch("/comfyui/settings")
        async def comfyui_settings_patch(
            body: ComfyUISettingsBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
            persist: bool = Query(default=True),
        ):
            """Update ComfyUI config fields live; persist=true writes config/comfyui.toml."""
            patch = body.model_dump(exclude_none=True)
            try:
                self.server.update_comfyui_settings(patch, persist=persist)
            except (ValueError, TypeError) as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return await self.server.play_comfyui_status()

        @self.app.post("/comfyui/test-connection")
        async def comfyui_test_connection(
            _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        ):
            """Ping the configured ComfyUI base_url and return reachability."""
            from fablestar.server import _ping_comfyui_http  # noqa: PLC0415
            c = self.server.config.comfyui
            ok, err = await _ping_comfyui_http(c.base_url)
            return {"reachable": ok, "base_url": c.base_url, "error": err or None}

        @self.app.post("/forge/generate")
        async def forge_generate(
            req: ForgeRequest,
            _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
        ):
            # 1. Render Prompt
            prompt = self.server.prompt_manager.render(
                "forge_room",
                user_seed=req.seed,
                room_type=req.room_type,
                room_depth=req.depth
            )
            
            # 2. Call LLM
            logger.info(f"Forge: Generating room from seed '{req.seed}'")
            raw_yaml = await self.server.llm_client.generate(prompt, max_tokens=2048)
            
            # 3. Clean and Validate
            try:
                # Ensure it's valid YAML
                parsed = yaml.safe_load(raw_yaml)
                return {"id": parsed.get("id"), "yaml": raw_yaml, "data": parsed}
            except Exception as e:
                logger.error(f"Forge: Failed to parse generated YAML: {e}")
                raise HTTPException(status_code=500, detail="LLM generated invalid YAML. Please retry.")

        @self.app.post("/forge/generate-area-prompt")
        async def forge_generate_area_prompt(
            req: ForgeAreaImagePromptRequest,
            _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
        ):
            """LM Studio / OpenAI-compatible: suggest a ComfyUI prompt from room description."""
            return await self.server.forge_suggest_area_image_prompt(
                req.room_name,
                req.room_type,
                req.depth,
                req.description_base,
            )

        @self.app.post("/forge/room-area-image")
        async def forge_room_area_image(
            req: ForgeRoomAreaImageRequest,
            _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
        ):
            """Generate room scene PNG via ComfyUI; returns area_image_url under /media/rooms/."""
            return await self.server.forge_generate_room_area_image(
                req.prompt,
                zone_id=req.zone_id,
                room_slug=req.room_slug,
            )

        @self.app.post("/forge/generate-content")
        async def forge_generate_content(
            req: ForgeGenericRequest,
            _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
        ):
            cat = (req.category or "misc").lower().strip().replace(" ", "_")
            if not cat.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid category")
            prompt = self.server.prompt_manager.render(
                "forge_generic",
                category=cat,
                seed=req.seed,
                context=req.context or {},
            )
            logger.info("Forge: generic generate category=%s", cat)
            raw_yaml = await self.server.llm_client.generate(
                prompt,
                system_prompt="You output only valid YAML for a MUD. No markdown.",
                max_tokens=3072,
            )
            try:
                parsed = yaml.safe_load(raw_yaml)
            except Exception as e:
                logger.error("Forge: generic YAML parse failed: %s", e)
                raise HTTPException(status_code=500, detail="LLM returned invalid YAML") from e
            return {"yaml": raw_yaml, "data": parsed, "category": cat}

        @self.app.post("/forge/inject")
        async def forge_inject(
            injection: ForgeInjection,
            ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
        ):
            # 1. Validate the path
            try:
                zone_id, room_filename = injection.id.split(":", 1)
                if not ctx.may_write_zone(zone_id):
                    raise HTTPException(status_code=403, detail="zone_denied")
                zone_dir = Path("content/world/zones") / zone_id / "rooms"
                zone_dir.mkdir(parents=True, exist_ok=True)
                
                file_path = zone_dir / f"{room_filename}.yaml"
                
                # 2. Write to disk
                await asyncio.to_thread(
                    file_path.write_text, injection.yaml_content, "utf-8"
                )
                
                logger.info(f"Forge: Injected room {injection.id} to {file_path}")
                return {"status": "success", "path": str(file_path)}
            except Exception as e:
                logger.error(f"Forge: Failed to inject room: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # ---- Entity Template Management ----------------------------------------

        @self.app.get("/content/entities")
        async def list_entity_templates(
            _ctx: Annotated[AdminContext, Depends(require_tool("entities"))],
        ):
            """List all entity templates defined on disk."""
            templates = self.server.content_loader.list_entity_templates()
            return [t.model_dump() for t in templates]

        @self.app.get("/content/entities/{entity_id}/yaml")
        async def get_entity_yaml(
            entity_id: str,
            _ctx: Annotated[AdminContext, Depends(require_tool("entities"))],
        ):
            """Return raw YAML for an entity template."""
            if not entity_id.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid entity id")
            path = Path("content/world/entities") / f"{entity_id}.yaml"
            if not path.is_file():
                raise HTTPException(status_code=404, detail="Entity not found")
            return {"yaml": path.read_text(encoding="utf-8")}

        @self.app.put("/content/entities/{entity_id}/yaml")
        async def save_entity_yaml(
            entity_id: str,
            body: ContentInjectBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("entities"))],
        ):
            """Write/overwrite an entity template YAML file."""
            if not entity_id.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid entity id")
            path = Path("content/world/entities") / f"{entity_id}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body.yaml_content, encoding="utf-8")
            self.server.content_loader.clear_cache()
            return {"status": "saved", "path": str(path)}

        @self.app.post("/content/entities/inject")
        async def inject_entity(
            body: ContentInjectBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("entities"))],
        ):
            """Save a new entity template to disk (path = 'entities/<id>')."""
            slug = body.path.lstrip("/").removeprefix("entities/").replace("/", "_")
            if not slug.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid path")
            path = Path("content/world/entities") / f"{slug}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body.yaml_content, encoding="utf-8")
            self.server.content_loader.clear_cache()
            return {"status": "injected", "path": str(path)}

        # ---- Item Template Management ------------------------------------------

        @self.app.get("/content/items/{item_id}/yaml")
        async def get_item_yaml(
            item_id: str,
            _ctx: Annotated[AdminContext, Depends(require_tool("items"))],
        ):
            """Return raw YAML for an item template."""
            if not item_id.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid item id")
            path = Path("content/world/items") / f"{item_id}.yaml"
            if not path.is_file():
                raise HTTPException(status_code=404, detail="Item not found")
            return {"yaml": path.read_text(encoding="utf-8")}

        @self.app.put("/content/items/{item_id}/yaml")
        async def save_item_yaml(
            item_id: str,
            body: ContentInjectBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("items"))],
        ):
            """Write/overwrite an item template YAML file."""
            if not item_id.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid item id")
            path = Path("content/world/items") / f"{item_id}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body.yaml_content, encoding="utf-8")
            self.server.content_loader.clear_cache()
            return {"status": "saved", "path": str(path)}

        @self.app.post("/content/items/inject")
        async def inject_item(
            body: ContentInjectBody,
            _ctx: Annotated[AdminContext, Depends(require_tool("items"))],
        ):
            """Save a new item template to disk (path = 'items/<id>')."""
            slug = body.path.lstrip("/").removeprefix("items/").replace("/", "_")
            if not slug.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid path")
            path = Path("content/world/items") / f"{slug}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body.yaml_content, encoding="utf-8")
            self.server.content_loader.clear_cache()
            return {"status": "injected", "path": str(path)}

        # ---- Room YAML editing -------------------------------------------------

        @self.app.put("/content/room/{zone_id}/{room_slug}/yaml")
        async def save_room_yaml(
            zone_id: str,
            room_slug: str,
            body: ContentInjectBody,
            ctx: Annotated[AdminContext, Depends(require_tool("locations"))],
        ):
            """Write/overwrite a room YAML file and invalidate cache."""
            from re import match
            if not ctx.may_write_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            if not match(r'^[a-zA-Z0-9_-]+$', zone_id) or not match(r'^[a-zA-Z0-9_-]+$', room_slug):
                raise HTTPException(status_code=400, detail="Invalid zone or room slug")
            path = Path("content/world/zones") / zone_id / "rooms" / f"{room_slug}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body.yaml_content, encoding="utf-8")
            self.server.content_loader.invalidate(path)
            return {"status": "saved", "path": str(path)}

        # ---- World builder (zone graph, positions, structured room CRUD) -----

        @self.app.get("/content/zones/{zone_id}/graph")
        async def content_zone_graph(
            zone_id: str,
            ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations", "world"))],
        ):
            if not ctx.may_read_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            if zone_id not in content_browser.list_zone_ids():
                raise HTTPException(status_code=404, detail="Zone not found")
            return content_browser.zone_graph(zone_id)

        @self.app.put("/content/zones/{zone_id}/positions")
        async def content_zone_positions(
            zone_id: str,
            body: ZonePositionsBody,
            ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations"))],
        ):
            if not ctx.may_write_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            try:
                path = content_browser.save_zone_positions(zone_id, body.positions)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return {"status": "ok", "path": path}

        @self.app.put("/content/zones/{zone_id}/rooms/{room_slug}")
        async def content_save_room_json(
            zone_id: str,
            room_slug: str,
            body: RoomJsonBody,
            ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations"))],
        ):
            if not ctx.may_write_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            try:
                path = content_browser.save_room_dict(zone_id, room_slug, body.room)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.invalidate(path)
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "saved", "path": str(path)}

        @self.app.post("/content/zones/{zone_id}/rooms")
        async def content_create_room(
            zone_id: str,
            body: CreateRoomBody,
            ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations"))],
        ):
            if not ctx.may_write_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            slug = (body.slug or "").strip()
            if not re.match(r"^[a-zA-Z0-9_-]+$", slug):
                raise HTTPException(status_code=400, detail="invalid_slug")
            try:
                path = content_browser.create_room(zone_id, slug, body.room or None)
            except FileExistsError:
                raise HTTPException(status_code=409, detail="room_exists") from None
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.invalidate(path)
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "created", "path": str(path), "slug": slug}

        @self.app.delete("/content/zones/{zone_id}/rooms/{room_slug}")
        async def content_delete_room(
            zone_id: str,
            room_slug: str,
            ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations"))],
        ):
            if not ctx.may_write_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            try:
                content_browser.delete_room(zone_id, room_slug)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Room not found") from None
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            path = Path("content/world/zones") / zone_id / "rooms" / f"{room_slug}.yaml"
            self.server.content_loader.invalidate(path)
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "deleted", "slug": room_slug}

        @self.app.get("/content/galaxy")
        async def content_galaxy(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            return content_browser.galaxy_overview()

        @self.app.get("/content/systems/{system_id}")
        async def content_system(
            system_id: str,
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            data = content_browser.system_detail(system_id)
            if data is None:
                raise HTTPException(status_code=404, detail="System not found")
            return data

        @self.app.get("/content/builder/search")
        async def content_builder_search(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world", "locations"))],
            q: str = "",
            limit: int = 30,
        ):
            cap = max(5, min(int(limit), 80))
            return content_browser.builder_search(q, cap)

        @self.app.post("/content/systems")
        async def content_create_system(
            body: CreateSystemBody,
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            sid = (body.id or "").strip()
            if not re.match(r"^[a-zA-Z0-9_-]+$", sid):
                raise HTTPException(status_code=400, detail="invalid_system_id")
            try:
                path = content_browser.create_system(
                    sid,
                    name=body.name,
                    x=body.x,
                    y=body.y,
                    z=body.z,
                    faction=body.faction,
                    security=body.security,
                    star_type=body.star_type,
                    star_name=body.star_name,
                    add_to_galaxy=body.add_to_galaxy,
                )
            except FileExistsError:
                raise HTTPException(status_code=409, detail="system_exists") from None
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.clear_cache()
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "created", "path": str(path), "id": sid}

        @self.app.put("/content/systems/{system_id}")
        async def content_put_system(
            system_id: str,
            body: SystemDocumentBody,
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            if not re.match(r"^[a-zA-Z0-9_-]+$", system_id):
                raise HTTPException(status_code=400, detail="invalid_system_id")
            try:
                path = content_browser.save_system_document(system_id, body.document)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.invalidate(path)
            self.server.content_loader.invalidate(content_browser.GALAXY_FILE)
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "saved", "path": str(path)}

        @self.app.post("/content/ships/create")
        async def content_create_ship(
            body: CreateShipBody,
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            sid = (body.id or "").strip()
            if not re.match(r"^[a-zA-Z0-9_-]+$", sid):
                raise HTTPException(status_code=400, detail="invalid_ship_id")
            try:
                path = content_browser.create_ship_template(sid, body.name, body.size)
            except FileExistsError:
                raise HTTPException(status_code=409, detail="ship_exists") from None
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.clear_cache()
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "created", "path": str(path), "id": sid}

        @self.app.get("/content/ships")
        async def content_ships_list(
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world", "entities"))],
        ):
            return {"ships": content_browser.list_ship_templates()}

        @self.app.get("/content/ships/{ship_id}/graph")
        async def content_ship_graph(
            ship_id: str,
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            return content_browser.ship_graph(ship_id)

        @self.app.put("/content/ships/{ship_id}/rooms/{room_local_id}")
        async def content_save_ship_room(
            ship_id: str,
            room_local_id: str,
            body: RoomJsonBody,
            _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
        ):
            try:
                path = content_browser.save_ship_room(ship_id, room_local_id, body.room)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Ship not found") from None
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            self.server.content_loader.clear_cache()
            self.server.last_content_reload_at = datetime.now(UTC).isoformat()
            return {"status": "saved", "path": str(path)}

        # ---- Live World State --------------------------------------------------

        @self.app.get("/world/rooms/{zone_id}/{room_slug}/state")
        async def room_live_state(
            zone_id: str,
            room_slug: str,
            ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        ):
            """Return the live state of a room: players, entities, floor items."""
            if not ctx.may_read_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            room_id = f"{zone_id}:{room_slug}"
            players = list(await self.server.redis.get_room_players(room_id))
            entity_ids = list(await self.server.redis.get_room_entities(room_id))
            item_ids = list(await self.server.redis.get_room_items(room_id))

            entities = []
            for eid in entity_ids:
                state = await self.server.redis.get_entity_state(eid)
                if state:
                    entities.append(state)

            items = []
            for iid in item_ids:
                state = await self.server.redis.get_item_state(iid)
                if state:
                    items.append(state)

            return {
                "room_id": room_id,
                "players": players,
                "entities": entities,
                "floor_items": items,
            }

        @self.app.post("/world/rooms/{zone_id}/{room_slug}/spawn")
        async def manual_spawn(
            zone_id: str,
            room_slug: str,
            body: SpawnRequest,
            ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        ):
            """Manually spawn an entity into a room."""
            if not ctx.may_write_zone(zone_id):
                raise HTTPException(status_code=403, detail="zone_denied")
            room_id = f"{zone_id}:{room_slug}"
            entity_id = await self.server.spawner.spawn_entity(room_id, body.template)
            if not entity_id:
                raise HTTPException(status_code=404, detail=f"Entity template '{body.template}' not found")
            state = await self.server.redis.get_entity_state(entity_id)
            return {"status": "spawned", "entity_id": entity_id, "state": state}

        @self.app.delete("/world/entities/{entity_id}")
        async def despawn_entity(
            entity_id: str,
            ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        ):
            """Remove a live entity from the world."""
            state = await self.server.redis.get_entity_state(entity_id)
            if not state:
                raise HTTPException(status_code=404, detail="Entity not found")
            room_id = state.get("room_id", "")
            if room_id and ":" in room_id:
                z = room_id.split(":", 1)[0]
                if not ctx.may_write_zone(z):
                    raise HTTPException(status_code=403, detail="zone_denied")
            await self.server.spawner.despawn_entity(entity_id, room_id)
            return {"status": "despawned", "entity_id": entity_id}

        @self.app.get("/world/entities")
        async def list_live_entities(
            _ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        ):
            """List all live entities currently in the world (scans occupied rooms)."""
            results = []
            seen_rooms: set[str] = set()
            for player_id in self.server.session_manager.player_to_session:
                room_id = await self.server.redis.get_player_location(player_id)
                if room_id and room_id not in seen_rooms:
                    seen_rooms.add(room_id)
                    entity_ids = await self.server.redis.get_room_entities(room_id)
                    for eid in entity_ids:
                        state = await self.server.redis.get_entity_state(eid)
                        if state:
                            results.append(state)
            return results

        # ---- Websockets --------------------------------------------------------

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

        @self.app.websocket("/ws/play")
        async def websocket_play(websocket: WebSocket):
            """Dedicated WebSocket for the MUD game client."""
            await websocket.accept()
            protocol = WebSocketProtocol(websocket)
            # Create session and run the loop directly — the WebSocket stays
            # open as long as this handler is awaiting (FastAPI keeps it alive).
            session = await self.server.session_manager.create_session(protocol)
            await self.server._session_loop(session)

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

    async def broadcast_log(self, message: str):
        """Send a log message to all connected admin consoles."""
        for ws in self._active_sockets:
            try:
                await ws.send_json({"type": "log", "content": message})
            except Exception:
                pass

    async def start(self):
        """Run the uvicorn server in the same event loop."""
        config = uvicorn.Config(
            self.app, 
            host="0.0.0.0", 
            port=self.server.config.server.websocket_port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        # Handle the server gracefully
        await server.serve()
