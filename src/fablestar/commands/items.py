"""Item commands — get, drop, inventory, and examine."""

import logging

from fablestar.commands.registry import command
from fablestar.network.session import Session

logger = logging.getLogger(__name__)


@command("inventory", aliases=["i", "inv"])
async def inventory(session: Session, args: list[str]):
    """List your carried inventory."""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return

    inv = await app_instance.redis.get_player_inventory(player_id)
    if not inv:
        await session.send("You are carrying nothing.")
        return

    await session.send("\r\n--- Inventory ---")
    for item in inv:
        name = item.get("name", item.get("template", "unknown item"))
        await session.send(f"  {name}")


@command("take", aliases=["get", "pick"])
async def take(session: Session, args: list[str]):
    """Pick up an item from the floor. Usage: take <item>"""
    from fablestar.app import app_instance

    if not args:
        await session.send("Take what? Usage: take <item>")
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
    found_id = None
    found_state = None
    for iid in item_ids:
        state = await app_instance.redis.get_item_state(iid)
        if state and target_name in state.get("name", "").lower():
            found_id = iid
            found_state = state
            break

    if not found_state:
        await session.send(f"You see no '{target_name}' here.")
        return

    # Move from floor to player inventory
    await app_instance.redis.remove_item_from_room(found_id, room_id)
    await app_instance.redis.delete_item_state(found_id)

    inv = await app_instance.redis.get_player_inventory(player_id)
    inv.append(
        {
            "id": found_id,
            "template": found_state.get("template"),
            "name": found_state.get("name"),
            "description": found_state.get("description", ""),
            "value": found_state.get("value", 0),
        }
    )
    await app_instance.redis.set_player_inventory(player_id, inv)
    await session.send(f"You pick up the {found_state['name']}.")


@command("drop", aliases=["discard"])
async def drop(session: Session, args: list[str]):
    """Drop an item from your inventory. Usage: drop <item>"""
    import uuid

    from fablestar.app import app_instance

    if not args:
        await session.send("Drop what? Usage: drop <item>")
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

    if found_item is None:
        await session.send(f"You are not carrying '{target_name}'.")
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
    }
    await app_instance.redis.set_item_state(item_id, floor_state)
    await app_instance.redis.add_item_to_room(item_id, room_id)
    await session.send(f"You drop the {found_item['name']}.")


@command("examine", aliases=["ex", "look at", "inspect"])
async def examine(session: Session, args: list[str]):
    """Examine something in the room. Usage: examine <target>"""
    from fablestar.app import app_instance

    if not args:
        await session.send("Examine what?")
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
                await session.send(f"\r\n{feature.description}")
                return

    # 2. Check live entities
    entity_ids = await app_instance.redis.get_room_entities(room_id)
    for eid in entity_ids:
        state = await app_instance.redis.get_entity_state(eid)
        if state and state.get("alive", True):
            if target_name in state.get("name", "").lower():
                tmpl = app_instance.content_loader.get_entity_template(state["template"])
                desc = (
                    tmpl.description.get("long", tmpl.description.get("short", ""))
                    if tmpl
                    else state["name"]
                )
                hp = state.get("hp", "?")
                max_hp = state.get("max_hp", "?")
                await session.send(f"\r\n{desc}")
                await session.send(f"[HP: {hp}/{max_hp}]")
                return

    # 3. Check floor items
    item_ids = await app_instance.redis.get_room_items(room_id)
    for iid in item_ids:
        state = await app_instance.redis.get_item_state(iid)
        if state and target_name in state.get("name", "").lower():
            await session.send(f"\r\n{state.get('description', 'An item.')}")
            return

    # 4. Check inventory
    inv = await app_instance.redis.get_player_inventory(player_id)
    for item in inv:
        if target_name in item.get("name", "").lower():
            await session.send(f"\r\n{item.get('description', 'An item you are carrying.')}")
            return

    await session.send(f"You see nothing notable called '{target_name}'.")
