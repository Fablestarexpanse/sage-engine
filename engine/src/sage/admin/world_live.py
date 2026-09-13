"""Best-effort Redis aggregates for admin /world/live (dev / ops)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _count_keys(client, match: str) -> int:
    n = 0
    async for _ in client.scan_iter(match=match, count=256):
        n += 1
    return n


async def build_world_live_snapshot(redis_client) -> dict[str, Any]:
    """
    Scan Redis for keys matching FableStar conventions. May be expensive on large DBs;
    intended for local / low-scale ops.
    """
    if redis_client is None:
        return {
            "redis_connected": False,
            "rooms_with_players": 0,
            "rooms_with_players_detail": [],
            "combat_keys": 0,
            "entity_state_keys": 0,
            "item_state_keys": 0,
            "note": "Redis client not initialized",
        }

    rooms_detail: list[dict[str, Any]] = []
    rooms_with_players = 0
    try:
        async for key in redis_client.scan_iter(match="room:*:players", count=256):
            cnt = await redis_client.scard(key)
            if cnt > 0:
                rooms_with_players += 1
                if len(rooms_detail) < 50:
                    rid = key
                    if rid.startswith("room:") and rid.endswith(":players"):
                        rid = rid[5 : -len(":players")]
                    rooms_detail.append({"room_id": rid, "player_count": cnt})
    except Exception as e:
        logger.debug("world_live room scan failed", exc_info=True)
        return {
            "redis_connected": True,
            "error": str(e),
            "rooms_with_players": 0,
            "rooms_with_players_detail": [],
            "combat_keys": 0,
            "entity_state_keys": 0,
            "item_state_keys": 0,
        }

    try:
        combat_keys = await _count_keys(redis_client, "combat:*")
        entity_state_keys = await _count_keys(redis_client, "entity:*:state")
        item_state_keys = await _count_keys(redis_client, "item:*:state")
    except Exception as e:
        logger.debug("world_live key counts failed", exc_info=True)
        return {
            "redis_connected": True,
            "error": str(e),
            "rooms_with_players": rooms_with_players,
            "rooms_with_players_detail": rooms_detail,
            "combat_keys": 0,
            "entity_state_keys": 0,
            "item_state_keys": 0,
        }

    return {
        "redis_connected": True,
        "rooms_with_players": rooms_with_players,
        "rooms_with_players_detail": sorted(
            rooms_detail, key=lambda x: (-x["player_count"], x["room_id"])
        ),
        "combat_keys": combat_keys,
        "entity_state_keys": entity_state_keys,
        "item_state_keys": item_state_keys,
        "note": "Best-effort SCAN; do not rely on for billing-scale accuracy.",
    }
