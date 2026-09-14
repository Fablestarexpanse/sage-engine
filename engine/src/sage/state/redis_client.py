"""RedisState — typed async accessors for all hot game state (locations, stats, entities, items)."""

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import redis.asyncio as redis

from sage.core.config import RedisConfig
from sage.state.state_types import EntityState, InventoryItem, ItemState

logger = logging.getLogger(__name__)


class RedisState:
    """Typed async accessors for all hot game state (locations, stats, entities, items).

    All public methods propagate ``redis.RedisError`` on connection failure
    — callers should catch it distinctly from a missing-key result (which
    returns None/empty collection, not an exception).
    """

    KEY_PREFIXES = {
        "player_location": "player:{id}:location",
        "player_session": "player:{id}:session",
        "player_stats": "player:{id}:stats",
        "player_inventory": "player:{id}:inventory",
        "room_players": "room:{id}:players",
        "room_entities": "room:{id}:entities",
        "room_items": "room:{id}:items",
        "combat": "combat:{id}",
        "entity_state": "entity:{id}:state",
        "item_state": "item:{id}:state",
        "search_finds": "search:{room_id}:{feature_id}:finds",
    }

    def __init__(self, config: RedisConfig):
        self.config = config
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        """The live Redis connection. Raises RuntimeError if connect() has not run."""
        if self._client is None:
            raise RuntimeError("RedisState is not connected — call connect() first")
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    async def connect(self):
        """Establish connection to the Redis server."""
        try:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                decode_responses=True,
            )
            await self._client.ping()
            logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """Close the Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Disconnected from Redis")

    async def get_all_active_player_ids(self) -> list[str]:
        """Return player IDs with an active location key (used for flush/persistence scans)."""
        keys = await self.client.keys(self._get_key("player_location", id="*"))
        return [k.split(":")[1] for k in keys]

    # --- Player Location Methods ---

    def _get_key(self, prefix_key: str, **kwargs: Any) -> str:
        return self.KEY_PREFIXES[prefix_key].format(**kwargs)

    async def get_player_location(self, player_id: str) -> str | None:
        key = self._get_key("player_location", id=player_id)
        return await self.client.get(key)

    async def set_player_location(self, player_id: str, room_id: str):
        # We need to manage both the player's location key and the room's player set
        old_room = await self.get_player_location(player_id)

        if old_room:
            await self.remove_player_from_room(player_id, old_room)

        key = self._get_key("player_location", id=player_id)
        await self.client.set(key, room_id)
        await self.add_player_to_room(player_id, room_id)

    async def get_room_players(self, room_id: str) -> set[str]:
        key = self._get_key("room_players", id=room_id)
        return await self.client.smembers(key)

    async def add_player_to_room(self, player_id: str, room_id: str):
        key = self._get_key("room_players", id=room_id)
        await self.client.sadd(key, player_id)

    async def remove_player_from_room(self, player_id: str, room_id: str):
        key = self._get_key("room_players", id=room_id)
        await self.client.srem(key, player_id)

    # --- Player Stats Methods ---

    async def get_player_stats(self, player_id: str) -> dict[str, Any]:
        """Shape documented by state_types.CharacterStats (returned as plain dict —
        the proficiency layer mutates it with dynamic keys)."""
        key = self._get_key("player_stats", id=player_id)
        raw = await self.client.get(key)
        if raw is None:
            return {}
        return json.loads(raw)

    async def set_player_stats(self, player_id: str, stats: Mapping[str, Any]):
        key = self._get_key("player_stats", id=player_id)
        await self.client.set(key, json.dumps(stats))

    # --- Player Inventory Methods ---

    async def get_player_inventory(self, player_id: str) -> list[InventoryItem]:
        key = self._get_key("player_inventory", id=player_id)
        raw = await self.client.get(key)
        if raw is None:
            return []
        return json.loads(raw)

    async def set_player_inventory(self, player_id: str, inventory: Sequence[Mapping[str, Any]]):
        key = self._get_key("player_inventory", id=player_id)
        await self.client.set(key, json.dumps(inventory))

    # --- Entity State Methods ---

    async def get_entity_state(self, entity_id: str) -> EntityState | None:
        key = self._get_key("entity_state", id=entity_id)
        raw = await self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_entity_state(self, entity_id: str, state: Mapping[str, Any]):
        key = self._get_key("entity_state", id=entity_id)
        await self.client.set(key, json.dumps(state))

    async def delete_entity_state(self, entity_id: str):
        key = self._get_key("entity_state", id=entity_id)
        await self.client.delete(key)

    async def get_room_entities(self, room_id: str) -> set[str]:
        key = self._get_key("room_entities", id=room_id)
        return await self.client.smembers(key)

    async def add_entity_to_room(self, entity_id: str, room_id: str):
        key = self._get_key("room_entities", id=room_id)
        await self.client.sadd(key, entity_id)

    async def remove_entity_from_room(self, entity_id: str, room_id: str):
        key = self._get_key("room_entities", id=room_id)
        await self.client.srem(key, entity_id)

    # --- Floor Item State Methods ---

    async def get_item_state(self, item_id: str) -> ItemState | None:
        key = self._get_key("item_state", id=item_id)
        raw = await self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_item_state(self, item_id: str, state: Mapping[str, Any]):
        key = self._get_key("item_state", id=item_id)
        await self.client.set(key, json.dumps(state))

    async def delete_item_state(self, item_id: str):
        key = self._get_key("item_state", id=item_id)
        await self.client.delete(key)

    # --- Search / Scavenge Methods ---

    async def get_search_finds(self, room_id: str, feature_id: str) -> int:
        key = self._get_key("search_finds", room_id=room_id, feature_id=feature_id)
        val = await self.client.get(key)
        return int(val) if val else 0

    async def incr_search_finds(self, room_id: str, feature_id: str, ttl_s: float) -> int:
        """Count one successful find; the key expires so the feature restocks itself."""
        key = self._get_key("search_finds", room_id=room_id, feature_id=feature_id)
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, int(ttl_s))
        return int(count)

    async def get_room_items(self, room_id: str) -> set[str]:
        key = self._get_key("room_items", id=room_id)
        return await self.client.smembers(key)

    async def add_item_to_room(self, item_id: str, room_id: str):
        key = self._get_key("room_items", id=room_id)
        await self.client.sadd(key, item_id)

    async def remove_item_from_room(self, item_id: str, room_id: str):
        key = self._get_key("room_items", id=room_id)
        await self.client.srem(key, item_id)
