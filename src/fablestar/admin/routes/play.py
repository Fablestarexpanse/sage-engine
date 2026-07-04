"""Player-facing routes — /play/* REST, bundled room-art media, and the /ws/play WebSocket.

Responses follow the shapes documented in ``fablestar.network.play_messages``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from fablestar.admin.route_helpers import limiter
from fablestar.network.websocket_protocol import WebSocketProtocol

if TYPE_CHECKING:
    from fablestar.server import FablestarServer


class PlayAuthBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)


class PlayAuthCharactersBody(BaseModel):
    username: str
    password: str = Field(..., min_length=8)


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


def build_play_router(server: FablestarServer) -> APIRouter:
    router = APIRouter()

    @router.get("/play/health")
    async def play_health():
        """Cheap check that player REST routes are live (no DB)."""
        return {"ok": True, "play_api": "v1", "proficiency_catalog": True}

    @router.get("/media/room-art/{zone_id}/{room_slug}/v/{filename}")
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

    @router.get("/media/room-art/{zone_id}/{slug}.png")
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

    @router.post("/play/auth/login")
    @limiter.limit("10/minute")
    async def play_auth_login(request: Request, body: PlayAuthBody):
        """Web player: validate credentials and list characters."""
        return await server.player.login(body.username, body.password)

    @router.post("/play/auth/register")
    @limiter.limit("5/minute")
    async def play_auth_register(request: Request, body: PlayAuthBody):
        """Web player: create account (add characters in the UI)."""
        return await server.player.register(body.username, body.password)

    @router.post("/play/auth/characters")
    async def play_auth_characters(body: PlayAuthCharactersBody):
        """Re-fetch character list and account fields for the authenticated player."""
        return await server.player.refresh_characters(body.username, body.password)

    @router.get("/play/comfyui/status")
    async def play_comfyui_status():
        """Whether ComfyUI portrait generation is configured."""
        return await server.scenes.comfyui_status()

    @router.post("/play/characters/portrait")
    async def play_character_portrait(body: PlayPortraitBody):
        """Generate a portrait via ComfyUI (optional); returns /media/portraits/... URL."""
        return await server.scenes.generate_portrait(
            body.username, body.password, body.appearance_prompt
        )

    @router.post("/play/characters/suggest-portrait-prompt")
    async def play_suggest_portrait_prompt(body: PlaySuggestPortraitPromptBody):
        """LLM: suggest a ComfyUI portrait prompt from character name and notes."""
        return await server.scenes.suggest_portrait_prompt(
            body.username,
            body.password,
            body.character_name,
            appearance_notes=body.appearance_notes,
        )

    @router.post("/play/characters/create")
    async def play_character_create(body: PlayCreateCharacterBody):
        """Create a new character for the account."""
        starter = body.starter_proficiencies
        if isinstance(starter, dict):
            coerced: dict[str, Any] = {str(k): v for k, v in starter.items()}
        else:
            coerced = {}
        return await server.player.create_character(
            body.username,
            body.password,
            body.name,
            portrait_prompt=body.portrait_prompt,
            portrait_url=body.portrait_url,
            starter_proficiencies=coerced if coerced else None,
        )

    @router.get("/play/proficiencies/catalog")
    async def play_proficiencies_catalog():
        """Public read-only leaf list for chargen skill picker."""
        from fablestar.proficiencies.starter import (
            STARTER_MAX_PER_LEAF,
            STARTER_POINTS_BUDGET,
            catalog_leaves_for_client,
        )

        reg = server.content_loader.get_proficiency_registry()
        leaves = catalog_leaves_for_client(reg)
        domains = sorted({x["domain"] for x in leaves})
        return {
            "budget": STARTER_POINTS_BUDGET,
            "max_per_leaf": STARTER_MAX_PER_LEAF,
            "domains": domains,
            "leaves": leaves,
        }

    @router.post("/play/characters/delete")
    async def play_character_delete(body: PlayDeleteCharacterBody):
        """Remove a character owned by the account."""
        return await server.player.delete_character(body.username, body.password, body.character_id)

    @router.post("/play/scene/suggest-prompt")
    async def play_scene_suggest_prompt(body: PlaySceneSuggestBody):
        """LLM: suggest a ComfyUI environment prompt from recent narrative text."""
        return await server.scenes.suggest_scene_prompt(
            body.username,
            body.password,
            narrative_context=body.narrative_context,
            room_hint=body.room_hint,
        )

    @router.post("/play/scene/generate")
    async def play_scene_generate(body: PlaySceneGenerateBody):
        """Run area ComfyUI workflow; returns scene_image_url under /media/rooms/."""
        return await server.scenes.generate_scene_image(
            body.username,
            body.password,
            body.scene_prompt,
            character_id=body.character_id,
        )

    @router.post("/play/scene/gallery")
    async def play_scene_gallery(body: PlaySceneGalleryListBody):
        """List scene images saved for this account (ComfyUI history)."""
        return await server.scenes.list_scene_gallery(body.username, body.password)

    @router.post("/play/scene/apply-gallery")
    async def play_scene_apply_gallery(body: PlaySceneApplyGalleryBody):
        """Apply a gallery image as this character's current scene art."""
        return await server.scenes.apply_scene_from_gallery(
            body.username,
            body.password,
            body.gallery_id,
            body.character_id,
        )

    @router.websocket("/ws/play")
    async def websocket_play(websocket: WebSocket):
        """Dedicated WebSocket for the MUD game client."""
        await websocket.accept()
        protocol = WebSocketProtocol(websocket)
        # Create session and run the loop directly — the WebSocket stays
        # open as long as this handler is awaiting (FastAPI keeps it alive).
        session = await server.session_manager.create_session(protocol)
        await server._session_loop(session)

    return router
