"""Content routes — /content/* browsing for zones, rooms, entities and items; template YAML
editing; creating zones and rooms. Structural room editing is WorldForge's job (owner G.6)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from sage.admin import content_browser, content_tables
from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_any_tool, require_tool

if TYPE_CHECKING:
    from sage.server import SageServer


class ContentInjectBody(BaseModel):
    """Write arbitrary YAML content to a file under content/world/."""

    path: str  # e.g. "entities/stalker" or "items/sword"
    yaml_content: str
    # Optimistic-concurrency token from the read endpoints; when set, the write is
    # rejected with 409 content_modified if the file changed on disk since it was read.
    expected_mtime: float | None = None


def build_content_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    def _mark_reloaded() -> None:
        server.last_content_reload_at = datetime.now(UTC).isoformat()

    @router.get("/content/overview")
    async def content_overview(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("world", "content", "dashboard"))],
    ):
        return content_browser.content_overview()

    @router.get("/content/zones")
    async def content_zones(
        _ctx: Annotated[AdminContext, Depends(require_tool("world"))],
    ):
        return content_browser.list_zones()

    @router.get("/content/zones/{zone_id}/rooms")
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

    @router.get("/content/rooms/{zone_id}/{room_slug}")
    async def content_room_detail(
        zone_id: str,
        room_slug: str,
        ctx: Annotated[AdminContext, Depends(require_tool("world"))],
    ):
        """One room: its YAML, parsed fields, and the content check's findings for it."""
        import asyncio

        from sage.world.lint import lint_world

        if not ctx.may_read_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")
        try:
            detail = content_browser.room_detail(zone_id, room_slug)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_slug") from None
        if detail is None:
            raise HTTPException(status_code=404, detail="room_not_found")
        report = await asyncio.to_thread(lint_world, server.world, zone_id)
        mine = (f"{detail['id']}:", f"{detail['id']} ", f"{zone_id}/{room_slug}.yaml:")
        detail["problems"] = {
            "errors": [e for e in report.errors if e.startswith(mine)],
            "warnings": [w for w in report.warnings if w.startswith(mine)],
        }
        return detail

    @router.get("/content/entities/spawns")
    async def content_entity_spawns(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("entities", "world"))],
    ):
        return content_browser.aggregate_entity_spawns()

    @router.get("/content/items")
    async def content_items(
        _ctx: Annotated[AdminContext, Depends(require_tool("items"))],
    ):
        return content_browser.list_items()

    @router.post("/content/cache/reload")
    async def content_cache_reload(
        _ctx: Annotated[AdminContext, Depends(require_tool("server"))],
    ):
        server.content_loader.clear_cache()
        server.prompt_manager.reload()
        _mark_reloaded()
        return {"status": "ok", "message": "Content and prompt caches cleared."}

    # ---- Entity / Item template management (shared factory) -----------------

    def _register_template_routes(kind: str, tool: str) -> None:
        """Register get/put/inject YAML routes for a flat template dir (entities, items)."""

        def base_dir() -> Path:
            return server.world.content_dir / "world" / kind

        label = kind[:-1].capitalize()  # "entities" -> "Entity"
        # A default value, not Annotated[...]: with postponed annotations FastAPI cannot see the
        # local `tool` inside a string annotation, and every call failed with 422 (_ctx query).
        tool_dependency = Depends(require_tool(tool))

        @router.get(f"/content/{kind}/{{template_id}}/yaml")
        async def get_template_yaml(
            template_id: str,
            _ctx: AdminContext = tool_dependency,
        ):
            if not template_id.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail=f"Invalid {label.lower()} id")
            path = base_dir() / f"{template_id}.yaml"
            if not path.is_file():
                raise HTTPException(status_code=404, detail=f"{label} not found")
            return {"yaml": path.read_text(encoding="utf-8")}

        @router.put(f"/content/{kind}/{{template_id}}/yaml")
        async def save_template_yaml(
            template_id: str,
            body: ContentInjectBody,
            _ctx: AdminContext = tool_dependency,
        ):
            try:
                path = content_browser.save_template_yaml_text(kind, template_id, body.yaml_content)
            except ValueError as e:
                detail = f"Invalid {label.lower()} id" if str(e) == "invalid_slug" else str(e)
                raise HTTPException(status_code=400, detail=detail) from None
            server.content_loader.clear_cache()
            return {"status": "saved", "path": str(path)}

        @router.post(f"/content/{kind}/inject")
        async def inject_template(
            body: ContentInjectBody,
            _ctx: AdminContext = tool_dependency,
        ):
            slug = body.path.lstrip("/").removeprefix(f"{kind}/").replace("/", "_")
            try:
                path = content_browser.save_template_yaml_text(kind, slug, body.yaml_content)
            except ValueError as e:
                detail = "Invalid path" if str(e) == "invalid_slug" else str(e)
                raise HTTPException(status_code=400, detail=detail) from None
            server.content_loader.clear_cache()
            return {"status": "injected", "path": str(path)}

    @router.get("/content/entities")
    async def list_entity_templates(
        _ctx: Annotated[AdminContext, Depends(require_tool("entities"))],
    ):
        """List all entity templates defined on disk (a file that does not parse is listed too)."""
        return content_browser.list_entity_template_rows()

    @router.get("/content/templates/{kind}")
    async def template_table(
        kind: str,
        ctx: Annotated[AdminContext, Depends(require_any_tool("entities", "items"))],
        q: str = "",
        type: str = "",
        sort: str = "name",
        desc: bool = False,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        """Entity or item templates as a table: columns from the model and plugin fields."""
        if kind not in content_tables.KINDS:
            raise HTTPException(status_code=404, detail="unknown_template_kind")
        if not ctx.may_use_tool(kind):
            raise HTTPException(status_code=403, detail=f"tool_denied:{kind}")
        extensions = getattr(getattr(server, "plugins", None), "extensions", None)
        schemas = extensions.schemas() if extensions is not None else {}
        # A thread: the first listing of a large world parses every file, and must not stall the
        # game loop this route shares.
        return await asyncio.to_thread(
            content_tables.table,
            kind,
            schemas,
            q=q,
            type_=type,
            sort=sort,
            desc=desc,
            limit=limit,
            offset=offset,
        )

    _register_template_routes("entities", "entities")
    _register_template_routes("items", "items")

    return router
