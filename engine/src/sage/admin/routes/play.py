"""Player-facing routes — /play/* REST, bundled room-art media, and the /ws/play WebSocket.

Responses follow the shapes documented in ``sage.network.play_messages``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from sage.admin.route_helpers import limiter
from sage.network.websocket_protocol import WebSocketProtocol
from sage.services.player_service import MIN_PASSWORD_LENGTH

if TYPE_CHECKING:
    from sage.server import SageServer


class DevLoginBody(BaseModel):
    character: str = Field(..., min_length=2, max_length=50)


class PlayAuthBody(BaseModel):
    username: str
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)


class PlayAuthCharactersBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)


class PlayCreateCharacterBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)
    name: str
    portrait_prompt: str = ""
    portrait_url: str = ""
    # World-defined creation choices (chargen.validate), e.g. {"proficiencies": {leaf: level}}.
    chargen: dict[str, Any] | None = None
    # Older clients: the proficiency allocation alone; treated as {"proficiencies": ...}.
    starter_proficiencies: dict[str, Any] | None = None


class PlayDeleteCharacterBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)
    character_id: int = Field(..., ge=1)


class PlayPortraitBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)
    appearance_prompt: str = ""


class PlaySuggestPortraitPromptBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)
    character_name: str = ""
    appearance_notes: str = ""


class PlaySceneSuggestBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)
    narrative_context: str = ""
    room_hint: str = ""


class PlaySceneGenerateBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)
    scene_prompt: str = ""
    character_id: int | None = None


class PlaySceneGalleryListBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)


class PlaySceneApplyGalleryBody(BaseModel):
    username: str = ""
    password: str = ""
    token: str = ""  # play session token from /play/auth/login (preferred over password)
    gallery_id: int = Field(..., ge=1)
    character_id: int = Field(..., ge=1)


_MEDIA_SEG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
_MEDIA_PNG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,120}\.png$")


def _room_art_file_response(zones_dir: Path, *parts: str) -> FileResponse:
    """Serve a room-art PNG under the world's zones directory, 404 on any traversal attempt."""
    path = zones_dir.joinpath(*parts).resolve()
    zones_root = zones_dir.resolve()
    try:
        path.relative_to(zones_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="not_found") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(path, media_type="image/png")


def build_play_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    @router.get("/play/health")
    async def play_health():
        """Cheap check that player REST routes are live (no DB)."""
        return {"ok": True, "play_api": "v1"}

    @router.get("/media/room-art/{zone_id}/{room_slug}/v/{filename}")
    async def media_room_art_variant(zone_id: str, room_slug: str, filename: str):
        """Scene art variant: zones/{zone}/rooms/art/{room}/{filename}.png"""
        if (
            not _MEDIA_SEG_RE.match(zone_id)
            or not _MEDIA_SEG_RE.match(room_slug)
            or not _MEDIA_PNG_RE.match(filename)
        ):
            raise HTTPException(status_code=404, detail="not_found")
        return _room_art_file_response(
            server.world.zones_dir, zone_id, "rooms", "art", room_slug, filename
        )

    @router.get("/media/room-art/{zone_id}/{slug}.png")
    async def media_room_art_png(zone_id: str, slug: str):
        """Legacy flat file: zones/{zone}/rooms/art/{slug}.png (bundled with zone)."""
        if not _MEDIA_SEG_RE.match(zone_id) or not _MEDIA_SEG_RE.match(slug):
            raise HTTPException(status_code=404, detail="not_found")
        return _room_art_file_response(
            server.world.zones_dir, zone_id, "rooms", "art", f"{slug}.png"
        )

    @router.post("/play/auth/login")
    @limiter.limit("10/minute")
    async def play_auth_login(request: Request, body: PlayAuthBody):
        """Web player: validate credentials and list characters."""
        return await server.player.login(body.username, body.password)

    def _dev_login_allowed(request: Request) -> bool:
        host = (request.client.host if request.client else "") or ""
        return server.player.dev_login_enabled() and host in ("127.0.0.1", "::1", "localhost")

    @router.get("/play/dev/status")
    async def play_dev_status(request: Request):
        """Whether passwordless dev login is available to this client."""
        return {"enabled": _dev_login_allowed(request)}

    @router.post("/play/dev/login")
    async def play_dev_login(request: Request, body: DevLoginBody):
        """Dev only: log in as (and create if needed) a test character without a password."""
        if not _dev_login_allowed(request):
            raise HTTPException(status_code=404, detail="not_found")
        return await server.player.dev_login(body.character)

    @router.post("/play/auth/register")
    @limiter.limit("5/minute")
    async def play_auth_register(request: Request, body: PlayAuthBody):
        """Web player: create account (add characters in the UI)."""
        return await server.player.register(body.username, body.password)

    @router.post("/play/auth/characters")
    async def play_auth_characters(body: PlayAuthCharactersBody):
        """Re-fetch character list and account fields for the authenticated player."""
        return await server.player.refresh_characters(
            body.username, body.password, token=body.token
        )

    @router.get("/play/comfyui/status")
    async def play_comfyui_status():
        """Whether ComfyUI portrait generation is configured."""
        return await server.scenes.comfyui_status()

    @router.post("/play/characters/portrait")
    async def play_character_portrait(body: PlayPortraitBody):
        """Generate a portrait via ComfyUI (optional); returns /media/portraits/... URL."""
        return await server.scenes.generate_portrait(
            body.username, body.password, body.appearance_prompt, token=body.token
        )

    @router.post("/play/characters/suggest-portrait-prompt")
    async def play_suggest_portrait_prompt(body: PlaySuggestPortraitPromptBody):
        """LLM: suggest a ComfyUI portrait prompt from character name and notes."""
        return await server.scenes.suggest_portrait_prompt(
            body.username,
            body.password,
            body.character_name,
            appearance_notes=body.appearance_notes,
            token=body.token,
        )

    @router.post("/play/characters/create")
    async def play_character_create(body: PlayCreateCharacterBody):
        """Create a new character for the account."""
        chargen = dict(body.chargen or {})
        if not chargen and isinstance(body.starter_proficiencies, dict):
            chargen = {"proficiencies": {str(k): v for k, v in body.starter_proficiencies.items()}}
        return await server.player.create_character(
            body.username,
            body.password,
            body.name,
            portrait_prompt=body.portrait_prompt,
            portrait_url=body.portrait_url,
            chargen=chargen or None,
            token=body.token,
        )

    @router.get("/play/chargen/options")
    async def play_chargen_options():
        """Public: the world's character-creation options (chargen.options slot)."""
        from sage.world.chargen import OPTIONS

        return server.resolvers.get(OPTIONS)()

    @router.post("/play/characters/delete")
    async def play_character_delete(body: PlayDeleteCharacterBody):
        """Remove a character owned by the account."""
        return await server.player.delete_character(
            body.username, body.password, body.character_id, token=body.token
        )

    @router.post("/play/scene/suggest-prompt")
    async def play_scene_suggest_prompt(body: PlaySceneSuggestBody):
        """LLM: suggest a ComfyUI environment prompt from recent narrative text."""
        return await server.scenes.suggest_scene_prompt(
            body.username,
            body.password,
            narrative_context=body.narrative_context,
            room_hint=body.room_hint,
            token=body.token,
        )

    @router.post("/play/scene/generate")
    async def play_scene_generate(body: PlaySceneGenerateBody):
        """Run area ComfyUI workflow; returns scene_image_url under /media/rooms/."""
        return await server.scenes.generate_scene_image(
            body.username,
            body.password,
            body.scene_prompt,
            character_id=body.character_id,
            token=body.token,
        )

    @router.post("/play/scene/gallery")
    async def play_scene_gallery(body: PlaySceneGalleryListBody):
        """List scene images saved for this account (ComfyUI history)."""
        return await server.scenes.list_scene_gallery(
            body.username, body.password, token=body.token
        )

    @router.post("/play/scene/apply-gallery")
    async def play_scene_apply_gallery(body: PlaySceneApplyGalleryBody):
        """Apply a gallery image as this character's current scene art."""
        return await server.scenes.apply_scene_from_gallery(
            body.username,
            body.password,
            body.gallery_id,
            body.character_id,
            token=body.token,
        )

    @router.websocket("/ws/play")
    async def websocket_play(websocket: WebSocket):
        """Dedicated WebSocket for the MUD game client."""
        await websocket.accept()
        protocol = WebSocketProtocol(websocket)
        # Create session and run the loop directly — the WebSocket stays
        # open as long as this handler is awaiting (FastAPI keeps it alive).
        session = await server.session_manager.create_session(protocol)
        await server.run_session_loop(session)

    return router
