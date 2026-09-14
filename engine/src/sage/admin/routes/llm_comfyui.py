"""AI backend routes — /llm/* (LM Studio / Ollama) and /comfyui/* settings + status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from sage.admin import comfyui_workflows
from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_tool

if TYPE_CHECKING:
    from sage.server import SageServer


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
    starting_ai_credits: int | None = None
    portrait_generation_cost: int | None = None
    area_generation_cost: int | None = None
    character_create_portrait_cost: int | None = None
    currency_display_name: str | None = None
    credits_per_usd: int | None = None


class WorkflowUploadBody(BaseModel):
    filename: str
    content: str
    overwrite: bool = False


class WorkflowAssignBody(BaseModel):
    role: str
    positive_prompt_node_id: str | None = None
    output_node_id: str | None = None
    persist: bool = True


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


def build_llm_comfyui_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    @router.get("/llm/config")
    async def llm_config(
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        return _llm_public_config(server.config)

    async def _compose_llm_status(*, refresh: bool) -> dict[str, Any]:
        snap = _llm_public_config(server.config)
        probe = await server.llm_client.status_dict(bypass_cache=refresh)
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

    @router.get("/llm/status")
    async def llm_status(
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        refresh: bool = Query(default=False),
    ):
        return await _compose_llm_status(refresh=refresh)

    @router.patch("/llm/settings")
    async def llm_settings_patch(
        body: LLMSettingsBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        persist: bool = Query(default=True),
    ):
        patch = body.model_dump(exclude_none=True)
        try:
            server.update_llm_settings(patch, persist=persist)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return await _compose_llm_status(refresh=True)

    @router.post("/llm/test-completion")
    async def llm_test_completion(
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Minimal chat completion to verify the pipeline (Forge / look use the same client)."""
        eff = await server.llm_client.effective_chat_model()
        text = await server.llm_client.generate(
            'Reply with exactly one word: "pong"',
            system_prompt="You follow instructions literally.",
            max_tokens=16,
        )
        return {
            "reply": text.strip(),
            "model": eff,
            "chat_model_config": server.config.llm.chat_model,
        }

    # ── ComfyUI settings ───────────────────────────────────────────────

    @router.get("/comfyui/status")
    async def comfyui_status(
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Full ComfyUI config + live reachability check."""
        return await server.scenes.comfyui_status()

    @router.patch("/comfyui/settings")
    async def comfyui_settings_patch(
        body: ComfyUISettingsBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
        persist: bool = Query(default=True),
    ):
        """Update ComfyUI config fields live; persist=true writes config/comfyui.toml."""
        patch = body.model_dump(exclude_none=True)
        try:
            server.update_comfyui_settings(patch, persist=persist)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return await server.scenes.comfyui_status()

    # ── ComfyUI workflow library ───────────────────────────────────────

    @router.get("/comfyui/workflows")
    async def comfyui_workflows_list(
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Workflow files the server can use, with validity and which role uses each."""
        return {"workflows": comfyui_workflows.list_workflows(server.config.comfyui)}

    @router.get("/comfyui/workflows/{name}")
    async def comfyui_workflow_detail(
        name: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Raw JSON plus the prompt/output/loader nodes found in it."""
        detail = comfyui_workflows.workflow_detail(name, server.config.comfyui)
        if detail is None:
            raise HTTPException(status_code=404, detail="workflow_not_found")
        return detail

    @router.post("/comfyui/workflows")
    async def comfyui_workflow_upload(
        body: WorkflowUploadBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Save an uploaded API-format workflow into config/comfyui_workflows/."""
        name = comfyui_workflows.slugify_name(body.filename)
        try:
            comfyui_workflows.save_workflow(name, body.content, overwrite=body.overwrite)
        except ValueError as e:
            code = 409 if str(e) == "name_taken" else 400
            raise HTTPException(status_code=code, detail=str(e)) from None
        return comfyui_workflows.workflow_detail(name, server.config.comfyui)

    @router.delete("/comfyui/workflows/{name}")
    async def comfyui_workflow_delete(
        name: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Delete an uploaded workflow that no role is using."""
        try:
            comfyui_workflows.delete_workflow(name, server.config.comfyui)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="workflow_not_found") from None
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        return {"deleted": name}

    @router.post("/comfyui/workflows/{name}/assign")
    async def comfyui_workflow_assign(
        name: str,
        body: WorkflowAssignBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Use this workflow for portraits or area scenes (node ids checked against the file)."""
        try:
            patch = comfyui_workflows.assignment_patch(
                name, body.role, body.positive_prompt_node_id, body.output_node_id
            )
            server.update_comfyui_settings(patch, persist=body.persist)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="workflow_not_found") from None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return await server.scenes.comfyui_status()

    @router.post("/comfyui/test-connection")
    async def comfyui_test_connection(
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        """Ping the configured ComfyUI base_url and return reachability."""
        c = server.config.comfyui
        ok, err = await server.scenes.ping()
        return {"reachable": ok, "base_url": c.base_url, "error": err or None}

    return router
