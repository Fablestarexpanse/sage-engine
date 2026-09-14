"""Content routes — /content/* YAML browsing/editing for zones, rooms, entities, items,
systems, ships and glyphs."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sage.admin import content_browser
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


class RoomJsonBody(BaseModel):
    """Full or partial room document merged into existing YAML."""

    room: dict[str, Any] = Field(default_factory=dict)
    # See ContentInjectBody.expected_mtime.
    expected_mtime: float | None = None


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


def build_content_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    def _mark_reloaded() -> None:
        server.last_content_reload_at = datetime.now(UTC).isoformat()

    def _check_room_write_conflict(
        zone_id: str, room_slug: str, expected_mtime: float | None
    ) -> None:
        """Advisory optimistic-concurrency check for room writes.

        WorldForge (and IDEs) write room YAML directly to disk, bypassing this API;
        rejecting a stale write here keeps admin-ui from silently clobbering those
        changes. Best-effort (stat-then-write), not a transactional lock.
        """
        if expected_mtime is None:
            return
        actual = content_browser.room_file_mtime(zone_id, room_slug)
        if actual is not None and abs(actual - expected_mtime) > 0.0005:
            raise HTTPException(status_code=409, detail="content_modified")

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

    @router.post("/content/zones")
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
        server.content_loader.clear_cache()
        _mark_reloaded()
        return {"status": "created", "id": zid, "path": str(rooms_path)}

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

    @router.get("/content/entities/spawns")
    async def content_entity_spawns(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "entities", "world"))],
    ):
        return content_browser.aggregate_entity_spawns()

    @router.get("/content/items")
    async def content_items(
        _ctx: Annotated[AdminContext, Depends(require_tool("items"))],
    ):
        return content_browser.list_items()

    @router.get("/content/glyphs")
    async def content_glyphs(
        _ctx: Annotated[AdminContext, Depends(require_tool("glyphs"))],
    ):
        return content_browser.list_glyphs()

    @router.get("/content/room/{zone_id}/{room_slug}/yaml")
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
        return {"yaml": raw, "mtime": content_browser.room_file_mtime(zone_id, room_slug)}

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

        @router.get(f"/content/{kind}/{{template_id}}/yaml")
        async def get_template_yaml(
            template_id: str,
            _ctx: Annotated[AdminContext, Depends(require_tool(tool))],
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
            _ctx: Annotated[AdminContext, Depends(require_tool(tool))],
        ):
            try:
                path = content_browser.save_template_yaml_text(kind, template_id, body.yaml_content)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid {label.lower()} id") from None
            server.content_loader.clear_cache()
            return {"status": "saved", "path": str(path)}

        @router.post(f"/content/{kind}/inject")
        async def inject_template(
            body: ContentInjectBody,
            _ctx: Annotated[AdminContext, Depends(require_tool(tool))],
        ):
            slug = body.path.lstrip("/").removeprefix(f"{kind}/").replace("/", "_")
            try:
                path = content_browser.save_template_yaml_text(kind, slug, body.yaml_content)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid path") from None
            server.content_loader.clear_cache()
            return {"status": "injected", "path": str(path)}

    @router.get("/content/entities")
    async def list_entity_templates(
        _ctx: Annotated[AdminContext, Depends(require_tool("entities"))],
    ):
        """List all entity templates defined on disk."""
        templates = server.content_loader.list_entity_templates()
        return [t.model_dump() for t in templates]

    _register_template_routes("entities", "entities")
    _register_template_routes("items", "items")

    # ---- Room YAML editing -------------------------------------------------

    @router.put("/content/room/{zone_id}/{room_slug}/yaml")
    async def save_room_yaml(
        zone_id: str,
        room_slug: str,
        body: ContentInjectBody,
        ctx: Annotated[AdminContext, Depends(require_tool("locations"))],
    ):
        """Write/overwrite a room YAML file and invalidate cache."""
        if not ctx.may_write_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")
        _check_room_write_conflict(zone_id, room_slug, body.expected_mtime)
        try:
            path = content_browser.save_room_yaml_text(zone_id, room_slug, body.yaml_content)
        except ValueError as e:
            detail = "Invalid zone or room slug" if str(e) == "invalid_slug" else str(e)
            raise HTTPException(status_code=400, detail=detail) from None
        server.content_loader.invalidate(path)
        return {"status": "saved", "path": str(path)}

    # ---- World builder (zone graph, positions, structured room CRUD) -----

    @router.get("/content/zones/{zone_id}/graph")
    async def content_zone_graph(
        zone_id: str,
        ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations", "world"))],
    ):
        if not ctx.may_read_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")
        if zone_id not in content_browser.list_zone_ids():
            raise HTTPException(status_code=404, detail="Zone not found")
        return content_browser.zone_graph(zone_id)

    @router.put("/content/zones/{zone_id}/positions")
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

    @router.put("/content/zones/{zone_id}/rooms/{room_slug}")
    async def content_save_room_json(
        zone_id: str,
        room_slug: str,
        body: RoomJsonBody,
        ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations"))],
    ):
        if not ctx.may_write_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")
        _check_room_write_conflict(zone_id, room_slug, body.expected_mtime)
        try:
            path = content_browser.save_room_dict(zone_id, room_slug, body.room)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        server.content_loader.invalidate(path)
        _mark_reloaded()
        return {"status": "saved", "path": str(path)}

    @router.post("/content/zones/{zone_id}/rooms")
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
        server.content_loader.invalidate(path)
        _mark_reloaded()
        return {"status": "created", "path": str(path), "slug": slug}

    @router.delete("/content/zones/{zone_id}/rooms/{room_slug}")
    async def content_delete_room(
        zone_id: str,
        room_slug: str,
        ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "locations"))],
        expected_mtime: float | None = None,
    ):
        if not ctx.may_write_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")
        _check_room_write_conflict(zone_id, room_slug, expected_mtime)
        try:
            content_browser.delete_room(zone_id, room_slug)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Room not found") from None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        path = server.world.zones_dir / zone_id / "rooms" / f"{room_slug}.yaml"
        server.content_loader.invalidate(path)
        _mark_reloaded()
        return {"status": "deleted", "slug": room_slug}

    # ---- Galaxy / systems / ships ------------------------------------------

    @router.get("/content/galaxy")
    async def content_galaxy(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
    ):
        return content_browser.galaxy_overview()

    @router.get("/content/systems/{system_id}")
    async def content_system(
        system_id: str,
        _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
    ):
        data = content_browser.system_detail(system_id)
        if data is None:
            raise HTTPException(status_code=404, detail="System not found")
        return data

    @router.get("/content/builder/search")
    async def content_builder_search(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world", "locations"))],
        q: str = "",
        limit: int = 30,
    ):
        cap = max(5, min(int(limit), 80))
        return content_browser.builder_search(q, cap)

    @router.post("/content/systems")
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
        server.content_loader.clear_cache()
        _mark_reloaded()
        return {"status": "created", "path": str(path), "id": sid}

    @router.put("/content/systems/{system_id}")
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
        server.content_loader.invalidate(path)
        server.content_loader.invalidate(content_browser.GALAXY_FILE)
        _mark_reloaded()
        return {"status": "saved", "path": str(path)}

    @router.post("/content/ships/create")
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
        server.content_loader.clear_cache()
        _mark_reloaded()
        return {"status": "created", "path": str(path), "id": sid}

    @router.get("/content/ships")
    async def content_ships_list(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world", "entities"))],
    ):
        return {"ships": content_browser.list_ship_templates()}

    @router.get("/content/ships/{ship_id}/graph")
    async def content_ship_graph(
        ship_id: str,
        _ctx: Annotated[AdminContext, Depends(require_any_tool("builder", "world"))],
    ):
        return content_browser.ship_graph(ship_id)

    @router.put("/content/ships/{ship_id}/rooms/{room_local_id}")
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
        server.content_loader.clear_cache()
        _mark_reloaded()
        return {"status": "saved", "path": str(path)}

    return router
