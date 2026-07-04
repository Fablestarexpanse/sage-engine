"""Info commands — look (with optional LLM narration) and help."""

from fablestar.commands.registry import command
from fablestar.llm.observation import build_room_fact_block
from fablestar.llm.validation import validator
from fablestar.network.session import Session


@command("look", aliases=["l"])
async def look(session: Session, args: list[str]):
    """Look at the current room or an object."""
    from fablestar.app import app_instance

    if not session.player_id:
        await session.send("Not authenticated.")
        return
    room_id = await app_instance.redis.get_player_location(session.player_id)
    if not room_id:
        await session.send("You are lost in the void.")
        return

    room = app_instance.content_loader.get_room(room_id)
    if room:
        await session.send(f"\r\n[ {room.id} ]")

        # 1. Generate Observations (Facts)
        observation_block = build_room_fact_block(room, {"time_of_day": "Eternal Night"})

        # 2. Render Prompt + Call LLM (non-fatal; falls back to base description)
        try:
            prompt = app_instance.prompt_manager.render(
                "room_description", observation_block=observation_block
            )
            narration = await app_instance.llm_client.generate(prompt)
            clean_narration = validator.sanitize(narration)
            await session.send(clean_narration)
        except Exception:
            await session.send(room.description.get("base", ""))

        if room.exits:
            exits_str = ", ".join(room.exits.keys())
            await session.send(f"Exits: {exits_str}")

        # 5. Show live entities (deterministic — no LLM)
        entity_ids = await app_instance.redis.get_room_entities(room_id)
        alive = []
        for eid in entity_ids:
            state = await app_instance.redis.get_entity_state(eid)
            if state and state.get("alive", True):
                alive.append(state["name"])
        if alive:
            await session.send(f"Entities: {', '.join(alive)}")

        # 6. Show floor items (deterministic)
        item_ids = await app_instance.redis.get_room_items(room_id)
        floor_items = []
        for iid in item_ids:
            state = await app_instance.redis.get_item_state(iid)
            if state:
                floor_items.append(state["name"])
        if floor_items:
            await session.send(f"Items on floor: {', '.join(floor_items)}")
    else:
        await session.send("You are in the void.")


@command("help", aliases=["h", "?"])
async def help_cmd(session: Session, args: list[str]):
    """Display available commands."""
    from fablestar.commands.registry import registry

    await session.send("--- Available Commands ---")
    cmds = sorted(registry._commands.keys())
    for cmd_name in cmds:
        cmd = registry.get(cmd_name)
        doc = cmd.handler.__doc__ or "No description."
        await session.send(f"{cmd_name.ljust(10)} - {doc.splitlines()[0]}")
