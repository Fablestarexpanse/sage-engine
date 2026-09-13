"""
Maestro event modules.

Each module is a dict:
    name      unique id
    interest  (ctx) -> int weight; 0 means "not applicable right now"
    fire      async (director, session, ctx) -> bool (False = nothing happened)

ctx: {"player_id", "stats", "room_id", "room" (the room model or None)}

Doctrine: mostly misery, occasional mercy — and every event must be something the player can
react to, never arbitrary insta-death.
"""

from __future__ import annotations

from typing import Any


def _hp_fraction(stats: dict[str, Any]) -> float:
    max_hp = max(1, int(stats.get("max_hp", stats.get("hp", 1) or 1)))
    return int(stats.get("hp", 0)) / max_hp


# --- Ambush: a spawn-capable room turns hostile while the player is healthy ---


def ambush_interest(ctx: dict[str, Any]) -> int:
    room = ctx.get("room")
    if room is None or not room.entity_spawns:
        return 0
    return 12 if _hp_fraction(ctx["stats"]) > 0.6 else 0


async def ambush_fire(director: Any, session: Any, ctx: dict[str, Any]) -> bool:
    api = director.api
    spawn = None
    for candidate in ctx["room"].entity_spawns:
        template = api.content.entity_template(candidate.template)
        # Only something hostile "lunges"; the room's own cap still holds, or every healthy
        # passer-by stacks another mob into the room.
        if template is None or director.hostile_tag not in (template.tags or set()):
            continue
        if await api.entities.count_in_room(ctx["room_id"], candidate.template) >= (
            candidate.max_count
        ):
            continue
        spawn = candidate
        break
    if spawn is None:
        return False
    entity_id = await api.entities.spawn(ctx["room_id"], spawn.template)
    if not entity_id:
        return False
    state = await api.entities.state(entity_id)
    name = (state or {}).get("name") or api.t("maestro.ambush_unnamed")
    await session.send(api.t("maestro.ambush", name=name))
    return True


# --- Mercy: a battered player stumbles onto supplies ---


def mercy_interest(ctx: dict[str, Any]) -> int:
    return 15 if _hp_fraction(ctx["stats"]) < 0.4 else 2


async def mercy_fire(director: Any, session: Any, ctx: dict[str, Any]) -> bool:
    if not director.mercy_item:
        return False
    item = await director.api.items.place(ctx["room_id"], director.mercy_item)
    if item is None:
        return False
    await session.send(director.api.t("maestro.mercy", item=item["name"]))
    return True


# --- Dread: pure atmosphere, keeps the world feeling watched ---


def dread_interest(ctx: dict[str, Any]) -> int:
    return 5


async def dread_fire(director: Any, session: Any, ctx: dict[str, Any]) -> bool:
    keys = director.api.lexicon_keys("maestro.dread.")
    if not keys:
        return False
    await session.send(director.api.t(director.rng.choice(keys)))
    return True


MODULES: list[dict[str, Any]] = [
    {"name": "ambush", "interest": ambush_interest, "fire": ambush_fire},
    {"name": "mercy", "interest": mercy_interest, "fire": mercy_fire},
    {"name": "dread", "interest": dread_interest, "fire": dread_fire},
]
