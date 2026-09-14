"""Item commands — get, drop, inventory, and examine."""

import logging
import time

from sage.commands.registry import command
from sage.lexicon import t
from sage.network.session import Session

logger = logging.getLogger(__name__)


async def _find_first_named(ids, fetch_state, target_name: str, *, require_alive: bool = False):
    """First (id, state) whose Redis state name contains target_name, else (None, None)."""
    for oid in ids:
        state = await fetch_state(oid)
        if not state:
            continue
        if require_alive and not state.get("alive", True):
            continue
        if target_name in state.get("name", "").lower():
            return oid, state
    return None, None


@command("inventory", aliases=["i", "inv"])
async def inventory(session: Session, args: list[str]):
    """List your carried inventory."""
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        return

    inv = await app_instance.redis.get_player_inventory(player_id)
    if not inv:
        await session.say("inventory.empty")
        return

    await session.say("inventory.header")
    for item in inv:
        name = item.get("name") or item.get("template") or t("items.unknown")
        await session.say("inventory.row", name=name)


@command("take", aliases=["get", "pick"])
async def take(session: Session, args: list[str]):
    """Pick up an item from the floor. Usage: take <item>"""
    from sage.app import app_instance

    if not args:
        await session.say("take.what")
        return

    player_id = session.player_id
    if not player_id:
        return

    target_name = " ".join(args).lower()
    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        return

    # Find matching item on floor
    item_ids = await app_instance.redis.get_room_items(room_id)
    found_id, found_state = await _find_first_named(
        item_ids, app_instance.redis.get_item_state, target_name
    )

    if found_state is None or found_id is None:
        await session.say("take.missing", name=target_name)
        return

    # Move from floor to player inventory
    await app_instance.redis.remove_item_from_room(found_id, room_id)
    await app_instance.redis.delete_item_state(found_id)

    inv = await app_instance.redis.get_player_inventory(player_id)
    inv.append(
        {
            "id": found_id,
            "template": found_state.get("template", ""),
            "name": found_state.get("name", ""),
            "description": found_state.get("description", ""),
            "value": found_state.get("value", 0),
        }
    )
    await app_instance.redis.set_player_inventory(player_id, inv)
    await session.say("take.done", name=found_state.get("name") or t("items.unnamed"))


@command("drop", aliases=["discard"])
async def drop(session: Session, args: list[str]):
    """Drop an item from your inventory. Usage: drop <item>"""
    import uuid

    from sage.app import app_instance

    if not args:
        await session.say("drop.what")
        return

    player_id = session.player_id
    if not player_id:
        return

    target_name = " ".join(args).lower()
    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        return

    inv = await app_instance.redis.get_player_inventory(player_id)
    found_idx = None
    found_item = None
    for i, item in enumerate(inv):
        if target_name in item.get("name", "").lower():
            found_idx = i
            found_item = item
            break

    if found_item is None or found_idx is None:
        await session.say("drop.missing", name=target_name)
        return

    inv.pop(found_idx)
    await app_instance.redis.set_player_inventory(player_id, inv)

    # Place on floor
    item_id = found_item.get("id") or f"{found_item.get('template', 'item')}_{uuid.uuid4().hex[:8]}"
    floor_state = {
        "id": item_id,
        "template": found_item.get("template"),
        "name": found_item.get("name"),
        "room_id": room_id,
        "description": found_item.get("description", ""),
        "value": found_item.get("value", 0),
        "weight": 0.0,
        "dropped_at": int(time.time()),
    }
    await app_instance.redis.set_item_state(item_id, floor_state)
    await app_instance.redis.add_item_to_room(item_id, room_id)
    await session.say("drop.done", name=found_item.get("name") or t("items.unnamed"))


_DIRECTION_ALIASES = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "u": "up",
    "d": "down",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
}


@command("examine", aliases=["ex", "inspect"])
async def examine(session: Session, args: list[str]):
    """Examine something in the room, an exit, or someone here. Usage: examine <target>"""
    from sage.app import app_instance

    while args and args[0] in ("at", "in", "the"):
        args = args[1:]
    if not args:
        await session.say("examine.what")
        return

    player_id = session.player_id
    if not player_id:
        return

    target_name = " ".join(args).lower()
    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        return

    room = app_instance.content_loader.get_room(room_id)

    # 1. Check room features
    if room:
        for feature in room.features:
            if target_name in feature.name.lower() or any(
                target_name in kw.lower() for kw in feature.keywords
            ):
                await session.say("examine.text", text=feature.description)
                return

    # 1b. Exits by direction
    if room:
        direction = _DIRECTION_ALIASES.get(target_name, target_name)
        exit_meta = room.exits.get(direction)
        if exit_meta is not None:
            text = (getattr(exit_meta, "description", "") or "").strip()
            await session.say(
                "examine.text", text=text or t("examine.exit_open", direction=direction)
            )
            return

    # 1c. Other players and agents here
    for other in sorted(await app_instance.redis.get_room_players(room_id)):
        if other == player_id or not other.lower().startswith(target_name):
            continue
        ostats = await app_instance.redis.get_player_stats(other)
        hp, max_hp = int(ostats.get("hp", 0) or 0), int(ostats.get("max_hp", 0) or 0)
        frac = hp / max_hp if max_hp else 1.0
        condition = t(
            "examine.unhurt"
            if frac >= 0.9
            else "examine.scraped"
            if frac >= 0.6
            else "examine.hurt"
            if frac >= 0.3
            else "examine.barely"
        )
        await session.say("examine.person", name=other, condition=condition)
        return

    # 2. Check live entities
    entity_ids = await app_instance.redis.get_room_entities(room_id)
    _, state = await _find_first_named(
        entity_ids, app_instance.redis.get_entity_state, target_name, require_alive=True
    )
    if state:
        tmpl = app_instance.content_loader.get_entity_template(state.get("template", ""))
        desc = (
            tmpl.description.get("long", tmpl.description.get("short", ""))
            if tmpl
            else state.get("name") or t("look.something")
        )
        hp = state.get("hp", "?")
        max_hp = state.get("max_hp", "?")
        await session.say("examine.text", text=desc)
        await session.say("examine.hp", hp=hp, max_hp=max_hp)
        return

    # 3. Check floor items
    item_ids = await app_instance.redis.get_room_items(room_id)
    _, istate = await _find_first_named(item_ids, app_instance.redis.get_item_state, target_name)
    if istate:
        await session.say("examine.text", text=istate.get("description") or t("examine.floor_item"))
        return

    # 4. Check inventory
    inv = await app_instance.redis.get_player_inventory(player_id)
    for item in inv:
        if target_name in item.get("name", "").lower():
            await session.say(
                "examine.text", text=item.get("description") or t("examine.carried_item")
            )
            return

    # Nothing matched — tell the player what IS examinable here instead of a dead end.
    examinable = [f.name for f in room.features] if room else []
    if examinable:
        await session.say(
            "examine.nothing_with_hints", name=target_name, names=", ".join(examinable)
        )
    else:
        await session.say("examine.nothing", name=target_name)
