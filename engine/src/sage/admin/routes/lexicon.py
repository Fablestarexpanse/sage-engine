"""Lexicon editing for Nexus: every player-facing string, live, versioned (decision 7).

GET    /admin/lexicon                 all keys with effective value, source and package default
GET    /admin/lexicon/{key}/history   saved versions, newest first
PUT    /admin/lexicon/{key}           save a new version and apply it immediately
POST   /admin/lexicon/{key}/rollback  re-activate an earlier version
DELETE /admin/lexicon/{key}           stop overriding; the world package value applies again
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_tool
from sage.lexicon.overrides import OverrideError

if TYPE_CHECKING:
    from sage.server import SageServer

MAX_VALUE_CHARS = 4000


class LexiconSaveBody(BaseModel):
    value: str = Field(max_length=MAX_VALUE_CHARS)
    note: str | None = Field(default=None, max_length=500)


class LexiconRollbackBody(BaseModel):
    version: int = Field(ge=1)


def build_lexicon_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    def _package_value(key: str) -> tuple[str | None, str | None]:
        """Value and source with live overrides ignored (what a rollback-to-default shows)."""
        for name, values in server.lexicon.layers:
            if name != "override" and key in values:
                return values[key], name
        return None, None

    def _known(key: str) -> None:
        if _package_value(key)[0] is None:
            raise HTTPException(status_code=404, detail="unknown_lexicon_key")

    @router.get("/admin/lexicon")
    async def list_lexicon(_ctx: Annotated[AdminContext, Depends(require_tool("lexicon"))]):
        rows = []
        for key in sorted(server.lexicon.keys()):
            default, default_source = _package_value(key)
            rows.append(
                {
                    "key": key,
                    "value": server.lexicon.get(key),
                    "source": server.lexicon.source(key),
                    "default": default,
                    "default_source": default_source,
                    "overridden": server.lexicon.source(key) == "override",
                }
            )
        return {"world": server.world.id, "keys": rows}

    @router.get("/admin/lexicon/{key}/history")
    async def lexicon_history(
        key: str, _ctx: Annotated[AdminContext, Depends(require_tool("lexicon"))]
    ):
        _known(key)
        return {"key": key, "versions": await server.lexicon_overrides.history(key)}

    @router.put("/admin/lexicon/{key}")
    async def save_lexicon(
        key: str,
        body: LexiconSaveBody,
        ctx: Annotated[AdminContext, Depends(require_tool("lexicon"))],
    ):
        _known(key)
        version = await server.lexicon_overrides.save(
            key, body.value, ctx.staff_id or None, body.note
        )
        await server.reload_lexicon_overrides()
        return {"key": key, "version": version, "value": server.lexicon.get(key)}

    @router.post("/admin/lexicon/{key}/rollback")
    async def rollback_lexicon(
        key: str,
        body: LexiconRollbackBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("lexicon"))],
    ):
        _known(key)
        try:
            await server.lexicon_overrides.rollback(key, body.version)
        except OverrideError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await server.reload_lexicon_overrides()
        return {"key": key, "version": body.version, "value": server.lexicon.get(key)}

    @router.delete("/admin/lexicon/{key}")
    async def clear_lexicon(
        key: str, _ctx: Annotated[AdminContext, Depends(require_tool("lexicon"))]
    ):
        _known(key)
        await server.lexicon_overrides.clear(key)
        await server.reload_lexicon_overrides()
        return {"key": key, "value": server.lexicon.get(key), "source": server.lexicon.source(key)}

    return router
