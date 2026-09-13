"""WorldForge routes — LLM room/content generation and the room-YAML write-through API."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sage.admin import content_browser
from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_tool
from sage.llm.client import LLMGenerationError

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)


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


def build_forge_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    @router.post("/forge/generate")
    async def forge_generate(
        req: ForgeRequest,
        _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
    ):
        # 1. Render Prompt
        prompt = server.prompt_manager.render(
            "forge_room", user_seed=req.seed, room_type=req.room_type, room_depth=req.depth
        )

        # 2. Call LLM
        logger.info(f"Forge: Generating room from seed '{req.seed}'")
        try:
            raw_yaml = await server.llm_client.generate_or_raise(prompt, max_tokens=2048)
        except LLMGenerationError as e:
            raise HTTPException(status_code=502, detail=f"LLM unavailable: {e}") from e

        # 3. Clean and Validate
        try:
            # Ensure it's valid YAML
            parsed = yaml.safe_load(raw_yaml)
            return {"id": parsed.get("id"), "yaml": raw_yaml, "data": parsed}
        except Exception as e:
            logger.error(f"Forge: Failed to parse generated YAML: {e}")
            raise HTTPException(status_code=500, detail="LLM generated invalid YAML. Please retry.")

    @router.post("/forge/generate-area-prompt")
    async def forge_generate_area_prompt(
        req: ForgeAreaImagePromptRequest,
        _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
    ):
        """LM Studio / OpenAI-compatible: suggest a ComfyUI prompt from room description."""
        return await server.scenes.forge_suggest_area_image_prompt(
            req.room_name,
            req.room_type,
            req.depth,
            req.description_base,
        )

    @router.post("/forge/room-area-image")
    async def forge_room_area_image(
        req: ForgeRoomAreaImageRequest,
        _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
    ):
        """Generate room scene PNG via ComfyUI; returns area_image_url under /media/rooms/."""
        return await server.scenes.generate_room_area_image(
            req.prompt,
            zone_id=req.zone_id,
            room_slug=req.room_slug,
        )

    @router.post("/forge/generate-content")
    async def forge_generate_content(
        req: ForgeGenericRequest,
        _ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
    ):
        cat = (req.category or "misc").lower().strip().replace(" ", "_")
        if not cat.replace("_", "").isalnum():
            raise HTTPException(status_code=400, detail="Invalid category")
        prompt = server.prompt_manager.render(
            "forge_generic",
            category=cat,
            seed=req.seed,
            context=req.context or {},
        )
        logger.info("Forge: generic generate category=%s", cat)
        try:
            raw_yaml = await server.llm_client.generate_or_raise(
                prompt,
                system_prompt="You output only valid YAML for a MUD. No markdown.",
                max_tokens=3072,
            )
        except LLMGenerationError as e:
            raise HTTPException(status_code=502, detail=f"LLM unavailable: {e}") from e
        try:
            parsed = yaml.safe_load(raw_yaml)
        except Exception as e:
            logger.error("Forge: generic YAML parse failed: %s", e)
            raise HTTPException(status_code=500, detail="LLM returned invalid YAML") from e
        return {"yaml": raw_yaml, "data": parsed, "category": cat}

    @router.post("/forge/inject")
    async def forge_inject(
        injection: ForgeInjection,
        ctx: Annotated[AdminContext, Depends(require_tool("forge"))],
    ):
        if ":" not in injection.id:
            raise HTTPException(status_code=400, detail="invalid_id")
        zone_id, room_filename = injection.id.split(":", 1)
        if not ctx.may_write_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")

        try:
            file_path = await asyncio.to_thread(
                content_browser.save_room_yaml_text, zone_id, room_filename, injection.yaml_content
            )
        except ValueError as e:
            detail = "invalid_id" if str(e) == "invalid_slug" else str(e)
            raise HTTPException(status_code=400, detail=detail) from None
        except OSError as e:
            logger.error(f"Forge: Failed to inject room: {e}")
            raise HTTPException(status_code=500, detail="write_failed")

        server.content_loader.invalidate(file_path)
        logger.info(f"Forge: Injected room {injection.id} to {file_path}")
        return {"status": "success", "path": str(file_path)}

    return router
