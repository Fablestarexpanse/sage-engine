"""Admin routes for the secondary LLM profile (config/agents_llm.toml): view, edit live, probe."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_tool

if TYPE_CHECKING:
    from sage.server import SageServer


class ProfileSettingsBody(BaseModel):
    enabled: bool | None = None
    primary_backend: str | None = None  # lm_studio | ollama | embedded
    lm_studio_url: str | None = None
    ollama_url: str | None = None
    chat_model: str | None = None
    model_path: str | None = None
    embedded_ctx: int | None = None
    temperature: float | None = None
    timeout_seconds: float | None = None


def build_llm_profiles_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    def _profile():
        profile = getattr(server, "llm_profile", None)
        if profile is None:
            raise HTTPException(status_code=503, detail="llm_profile_unavailable")
        return profile

    @router.get("/admin/agents-llm")
    async def profile_get(_ctx: Annotated[AdminContext, Depends(require_tool("agents"))]):
        return _profile().status()

    @router.put("/admin/agents-llm")
    async def profile_put(
        body: ProfileSettingsBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        from sage.core.config import AgentsLLMConfig
        from sage.llm.profile_persist import save_agents_llm_toml
        from sage.llm.profiles import BACKENDS

        profile = _profile()
        current = profile.config.model_dump()
        patch = body.model_dump(exclude_unset=True, exclude_none=True)
        if "primary_backend" in patch and patch["primary_backend"] not in BACKENDS:
            raise HTTPException(status_code=400, detail="unknown_backend")
        current.update(patch)
        try:
            new_cfg = AgentsLLMConfig(**current)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid_settings: {exc}") from exc
        save_agents_llm_toml(new_cfg)
        profile.reconfigure(new_cfg)
        return profile.status()

    @router.post("/admin/agents-llm/test")
    async def profile_test(_ctx: Annotated[AdminContext, Depends(require_tool("agents"))]):
        return await _profile().probe(
            "Say exactly one short in-character line greeting a stranger."
        )

    return router
