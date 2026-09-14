"""Console-wide search (/admin/search) and what points at a record (/content/references/...)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sage.admin import references, search
from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import get_admin_ctx, require_any_tool

if TYPE_CHECKING:
    from sage.server import SageServer

# The tool that opens each kind of record.
_TOOLS = {"items": "items", "entities": "entities", "rooms": "world"}


def build_search_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    @router.get("/admin/search")
    async def admin_search(
        request: Request, q: str = "", limit: int = Query(default=8, ge=1, le=50)
    ):
        """Characters, accounts, rooms, items, creatures and lexicon keys matching q, by kind."""
        return await search.search(server, get_admin_ctx(request), q, limit)

    @router.get("/content/references/{kind}/{record_id}")
    async def content_references(
        kind: str,
        record_id: str,
        ctx: Annotated[AdminContext, Depends(require_any_tool("items", "entities", "world"))],
    ):
        """Content that names the record, and the saved and live state holding it."""
        if kind not in _TOOLS:
            raise HTTPException(status_code=404, detail="unknown_record_kind")
        if not ctx.may_use_tool(_TOOLS[kind]):
            raise HTTPException(status_code=403, detail=f"tool_denied:{_TOOLS[kind]}")
        used_by = await asyncio.to_thread(references.content_references, record_id)
        return {
            "id": record_id,
            "used_by": used_by[: references.MAX_ROWS],
            "used_by_total": len(used_by),
            "live": await references.live_references(server, kind, record_id),
        }

    return router
