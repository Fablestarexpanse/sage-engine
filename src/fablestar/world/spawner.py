"""EntitySpawnManager — per-tick NPC respawn logic and entity kill/loot handling."""

import logging
import random
import uuid
from typing import TYPE_CHECKING

from fablestar.state.state_types import EntityState, ItemState

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)

# Check spawns every 20 ticks (~5 seconds at 4Hz)
SPAWN_CHECK_INTERVAL = 20


class EntitySpawnManager:
    """
    Manages live entity spawning and despawning.

    Runs on the tick loop. Only checks rooms that currently have players —
    no point spawning in empty rooms. Entity state lives in Redis so it is
    fast and ephemeral (respawns cleanly on server restart).
    """

    def __init__(self, server: "FablestarServer"):
        self.server = server

    # ------------------------------------------------------------------
    # Tick handler
    # ------------------------------------------------------------------

    async def on_tick(self, tick_count: int):
        if tick_count % SPAWN_CHECK_INTERVAL != 0:
            return

        # Find all rooms that have at least one player
        occupied_rooms: set[str] = set()
        for player_id in self.server.session_manager.player_to_session:
            room_id = await self.server.redis.get_player_location(player_id)
            if room_id:
                occupied_rooms.add(room_id)

        for room_id in occupied_rooms:
            await self._check_spawns(room_id)

    # ------------------------------------------------------------------
    # Internal spawn logic
    # ------------------------------------------------------------------

    async def _check_spawns(self, room_id: str):
        room = self.server.content_loader.get_room(room_id)
        if not room or not room.entity_spawns:
            return

        for spawn_def in room.entity_spawns:
            current_count = await self._count_template_in_room(room_id, spawn_def.template)
            if current_count >= spawn_def.max_count:
                continue
            if random.random() > spawn_def.chance:
                continue
            entity_id = await self.spawn_entity(room_id, spawn_def.template)
            if entity_id:
                logger.debug(f"Spawner: spawned {spawn_def.template} ({entity_id}) in {room_id}")

    async def _count_template_in_room(self, room_id: str, template: str) -> int:
        entity_ids = await self.server.redis.get_room_entities(room_id)
        count = 0
        for eid in entity_ids:
            state = await self.server.redis.get_entity_state(eid)
            if state and state.get("template") == template and state.get("alive", True):
                count += 1
        return count

    # ------------------------------------------------------------------
    # Public spawn / despawn API
    # ------------------------------------------------------------------

    async def spawn_entity(self, room_id: str, template_id: str) -> str | None:
        """Spawn one entity of the given template into a room. Returns the entity_id."""
        tmpl = self.server.content_loader.get_entity_template(template_id)
        if not tmpl:
            logger.warning(f"Spawner: unknown entity template '{template_id}'")
            return None

        entity_id = f"{template_id}_{uuid.uuid4().hex[:8]}"
        stats = dict(tmpl.stats)
        state: EntityState = {
            "id": entity_id,
            "template": template_id,
            "name": tmpl.name,
            "room_id": room_id,
            "hp": stats.get("hp", 10),
            "max_hp": stats.get("max_hp", stats.get("hp", 10)),
            "attack": stats.get("attack", 3),
            "defense": stats.get("defense", 1),
            "alive": True,
            "loot": list(tmpl.loot),
        }
        await self.server.redis.set_entity_state(entity_id, state)
        await self.server.redis.add_entity_to_room(entity_id, room_id)
        return entity_id

    async def despawn_entity(self, entity_id: str, room_id: str):
        """Remove an entity from the world entirely."""
        await self.server.redis.remove_entity_from_room(entity_id, room_id)
        await self.server.redis.delete_entity_state(entity_id)
        logger.debug(f"Spawner: despawned {entity_id} from {room_id}")

    async def kill_entity(self, entity_id: str, room_id: str) -> list[str]:
        """
        Mark an entity as dead, drop its loot onto the floor, then despawn it.
        Returns list of floor item IDs that were created.
        """
        state = await self.server.redis.get_entity_state(entity_id)
        if not state:
            return []

        dropped: list[str] = []
        for item_template_id in state.get("loot", []):
            if random.random() < 0.6:  # 60% drop chance per loot entry
                item_id = await self._drop_item(room_id, item_template_id)
                if item_id:
                    dropped.append(item_id)

        await self.despawn_entity(entity_id, room_id)
        return dropped

    async def _drop_item(self, room_id: str, template_id: str) -> str | None:
        tmpl = self.server.content_loader.get_item_template(template_id)
        if not tmpl:
            return None
        item_id = f"{template_id}_{uuid.uuid4().hex[:8]}"
        item_state: ItemState = {
            "id": item_id,
            "template": template_id,
            "name": tmpl.name,
            "room_id": room_id,
            "description": tmpl.description,
            "value": tmpl.value,
            "weight": tmpl.weight,
        }
        await self.server.redis.set_item_state(item_id, item_state)
        await self.server.redis.add_item_to_room(item_id, room_id)
        logger.debug(f"Spawner: dropped {item_id} in {room_id}")
        return item_id
