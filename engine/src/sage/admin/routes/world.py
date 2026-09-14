"""Live world routes: Redis snapshot, room state, creatures, floor items, spawn and clean-up."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from sage.admin import world_live
from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_any_tool, require_tool

if TYPE_CHECKING:
    from sage.server import SageServer


class SpawnRequest(BaseModel):
    template: str  # entity template ID to spawn


def build_world_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    @router.get("/world/live")
    async def world_live_view(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("operations", "world"))],
    ):
        return await world_live.world_live_snapshot(server)

    @router.post("/world/occupants/clear-offline")
    async def clear_offline_occupants(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("operations", "world"))],
    ):
        """Remove names that are not connected from room player sets (they show to the room)."""
        return {"removed": await world_live.clear_offline_occupants(server)}

    @router.get("/world/rooms/{zone_id}/{room_slug}/state")
    async def room_live_state(
        zone_id: str,
        room_slug: str,
        ctx: Annotated[AdminContext, Depends(require_tool("world"))],
    ):
        """Return the live state of a room: players, entities, floor items."""
        if not ctx.may_read_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")
        room_id = f"{zone_id}:{room_slug}"
        players = list(await server.redis.get_room_players(room_id))
        entity_ids = list(await server.redis.get_room_entities(room_id))
        item_ids = list(await server.redis.get_room_items(room_id))

        entities = []
        for eid in entity_ids:
            state = await server.redis.get_entity_state(eid)
            if state:
                entities.append(state)

        items = []
        for iid in item_ids:
            istate = await server.redis.get_item_state(iid)
            if istate:
                items.append(istate)

        return {
            "room_id": room_id,
            "players": players,
            "entities": entities,
            "floor_items": items,
        }

    @router.post("/world/rooms/{zone_id}/{room_slug}/spawn")
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
        entity_id = await server.spawner.spawn_entity(room_id, body.template)
        if not entity_id:
            raise HTTPException(
                status_code=404, detail=f"Entity template '{body.template}' not found"
            )
        state = await server.redis.get_entity_state(entity_id)
        return {"status": "spawned", "entity_id": entity_id, "state": state}

    @router.delete("/world/entities/{entity_id}")
    async def despawn_entity(
        entity_id: str,
        ctx: Annotated[AdminContext, Depends(require_tool("world"))],
    ):
        """Remove a live entity from the world."""
        state = await server.redis.get_entity_state(entity_id)
        if not state:
            raise HTTPException(status_code=404, detail="Entity not found")
        room_id = state.get("room_id", "")
        if room_id and ":" in room_id:
            z = room_id.split(":", 1)[0]
            if not ctx.may_write_zone(z):
                raise HTTPException(status_code=403, detail="zone_denied")
        await server.spawner.despawn_entity(entity_id, room_id)
        return {"status": "despawned", "entity_id": entity_id}

    @router.get("/world/entities")
    async def list_live_entities(
        _ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        limit: int = Query(default=world_live.DEFAULT_LIMIT, ge=1, le=5000),
    ):
        """Every live creature in Redis (rows up to limit, total counts all)."""
        return await world_live.live_creatures(server, limit)

    @router.get("/world/items")
    async def list_floor_items(
        _ctx: Annotated[AdminContext, Depends(require_tool("world"))],
        limit: int = Query(default=world_live.DEFAULT_LIMIT, ge=1, le=5000),
    ):
        """Items lying on room floors (rows up to limit, total counts all)."""
        return await world_live.floor_items(server, limit)

    @router.delete("/world/rooms/{zone_id}/{room_slug}/items/{item_id}")
    async def remove_floor_item(
        zone_id: str,
        room_slug: str,
        item_id: str,
        ctx: Annotated[AdminContext, Depends(require_tool("world"))],
    ):
        """Take an item off a room's floor and delete its live state."""
        if not ctx.may_write_zone(zone_id):
            raise HTTPException(status_code=403, detail="zone_denied")
        if not await world_live.remove_floor_item(server, f"{zone_id}:{room_slug}", item_id):
            raise HTTPException(status_code=404, detail="item_not_on_floor")
        return {"status": "removed", "item_id": item_id}

    return router
