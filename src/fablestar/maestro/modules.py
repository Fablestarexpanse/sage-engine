"""
Maestro event modules.

Each module is a dict:
    name      unique id
    interest  (ctx) -> int weight; 0 means "not applicable right now"
    fire      async (server, session, ctx) -> bool (False = nothing happened)

ctx: {"player_id", "stats", "room_id", "room" (RoomModel | None)}

Epitaph's doctrine: mostly misery, occasional mercy — and every event must
be something the player can react to, never arbitrary insta-death.
"""

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _hp_fraction(stats: dict[str, Any]) -> float:
    max_hp = max(1, int(stats.get("max_hp", stats.get("hp", 1) or 1)))
    return int(stats.get("hp", 0)) / max_hp


# --- Ambush: a spawn-capable room turns hostile while the player is healthy ---


def _ambush_interest(ctx: dict[str, Any]) -> int:
    room = ctx.get("room")
    if room is None or not room.entity_spawns:
        return 0
    return 12 if _hp_fraction(ctx["stats"]) > 0.6 else 0


async def _ambush_fire(server, session, ctx: dict[str, Any]) -> bool:
    room = ctx["room"]
    spawn = room.entity_spawns[0]
    entity_id = await server.spawner.spawn_entity(ctx["room_id"], spawn.template)
    if not entity_id:
        return False
    state = await server.redis.get_entity_state(entity_id)
    name = (state or {}).get("name", "something hostile")
    await session.send(f"\r\nMovement in the shadows — {name} lunges into the open!")
    return True


# --- Mercy: a battered player stumbles onto supplies ---


def _mercy_interest(ctx: dict[str, Any]) -> int:
    return 15 if _hp_fraction(ctx["stats"]) < 0.4 else 2


async def _mercy_fire(server, session, ctx: dict[str, Any]) -> bool:
    template = server.content_loader.get_item_template("ration_pack")
    if template is None:
        return False
    item_id = f"{template.id}_{uuid.uuid4().hex[:8]}"
    await server.redis.set_item_state(
        item_id,
        {
            "id": item_id,
            "template": template.id,
            "name": template.name,
            "description": template.description,
            "value": template.value,
        },
    )
    await server.redis.add_item_to_room(item_id, ctx["room_id"])
    await session.send(
        f"\r\nTucked behind a panel, something catches your eye: {template.name}. "
        "Someone's stash, once."
    )
    return True


# --- Dread: pure atmosphere, keeps the station feeling watched ---

_DREAD_LINES = [
    "Somewhere far below, metal shrieks against metal, then goes quiet.",
    "The lights dim for half a heartbeat. Nothing admits to it.",
    "A pressure door cycles in the distance — no one scheduled that.",
    "For a moment you are sure something in the walls is keeping pace with you.",
]


def _dread_interest(ctx: dict[str, Any]) -> int:
    return 5


async def _dread_fire(server, session, ctx: dict[str, Any]) -> bool:
    line = server.maestro.rng.choice(_DREAD_LINES)
    await session.send(f"\r\n{line}")
    return True


MODULES: list[dict[str, Any]] = [
    {"name": "ambush", "interest": _ambush_interest, "fire": _ambush_fire},
    {"name": "mercy", "interest": _mercy_interest, "fire": _mercy_fire},
    {"name": "dread", "interest": _dread_interest, "fire": _dread_fire},
]
