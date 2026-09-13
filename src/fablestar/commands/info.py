"""Info commands — look (with optional LLM narration) and help."""

import logging

from fablestar.commands.registry import command
from fablestar.llm.observation import build_room_fact_block
from fablestar.llm.validation import validator
from fablestar.network.session import Session

logger = logging.getLogger(__name__)


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
        header = f"{room.name} [ {room.id} ]" if room.name else f"[ {room.id} ]"
        await session.send(f"\r\n{header}")

        # Deterministic description immediately — the LLM must never make a
        # player wait to see the room. Narration arrives after, labeled, so a
        # late line can't masquerade as the response to the next command.
        await session.send(room.description.get("base", ""))

        observation_block = build_room_fact_block(room, {"time_of_day": "Eternal Night"})

        async def _narrate():
            try:
                prompt = app_instance.prompt_manager.render(
                    "room_description", observation_block=observation_block
                )
                narration = await app_instance.llm_client.generate_or_raise(prompt)
                clean = validator.sanitize(narration)
                if clean and clean.strip():
                    await session.send(f"\r\nThe scene: {clean.strip()}")
            except Exception as e:
                logger.debug("Room narration skipped: %s", e)

        # Agents parse facts, not prose — their constant looks would flood
        # the narration backend (and stall ticks on the embedded model).
        if not getattr(session, "is_agent", False):
            import asyncio as _asyncio

            _asyncio.get_running_loop().create_task(_narrate())

        if room.exits:
            exits_str = ", ".join(room.exits.keys())
            await session.send(f"Exits: {exits_str}")

        # 4b. Other players and agents present (deterministic)
        room_players = await app_instance.redis.get_room_players(room_id)
        others = sorted(p for p in room_players if p != session.player_id)
        if others:
            await session.send(f"Also here: {', '.join(others)}")

        # 5. Show live entities (deterministic — no LLM)
        entity_ids = await app_instance.redis.get_room_entities(room_id)
        alive = []
        for eid in entity_ids:
            state = await app_instance.redis.get_entity_state(eid)
            if state and state.get("alive", True):
                alive.append(state.get("name", "something"))
        if alive:
            await session.send(f"Entities: {', '.join(alive)}")

        # 6. Show floor items (deterministic)
        item_ids = await app_instance.redis.get_room_items(room_id)
        floor_items = []
        for iid in item_ids:
            istate = await app_instance.redis.get_item_state(iid)
            if istate:
                floor_items.append(istate.get("name", "something"))
        if floor_items:
            await session.send(f"Items on floor: {', '.join(floor_items)}")
    else:
        await session.send("You are in the void.")


@command("map", aliases=["chart"])
async def map_cmd(session: Session, args: list[str]):
    """Show the zone map: where you are and what you've explored. Usage: map"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        await session.send("You are nowhere mappable.")
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    visited = set(stats.get("visited_rooms") or [])
    data = app_instance._zone_map(room_id, visited)
    if not data:
        await session.send("No chart exists for this place.")
        return
    lines = [f"--- {data['zone']} ---"]
    for r in sorted(data["rooms"], key=lambda x: x["name"]):
        marker = "@" if r["id"] == data["current"] else ("*" if r["visited"] else "?")
        name = r["name"] if r["visited"] or r["id"] == data["current"] else "unexplored"
        lines.append(f"  [{marker}] {name}")
    lines.append("@ you are here · * explored · ? unexplored")
    await session.send("\r\n".join(lines))


@command("help", aliases=["h", "?"])
async def help_cmd(session: Session, args: list[str]):
    """Display available commands. Usage: help [command]"""
    from fablestar.commands.registry import registry

    if args:
        wanted = args[0].lower()
        cmd = registry.get(wanted)
        if cmd is None:
            await session.send(f"No command called '{wanted}'. Plain 'help' lists them all.")
            return
        doc = (cmd.handler.__doc__ or "No description.").strip()
        aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        await session.send(f"{wanted}{aliases}\r\n  {doc}")
        return

    await session.send("--- Available Commands ---")
    cmds = sorted(registry._commands.keys())
    for cmd_name in cmds:
        cmd = registry.get(cmd_name)
        if cmd is None:
            continue
        doc = cmd.handler.__doc__ or "No description."
        label = cmd_name if not cmd.aliases else f"{cmd_name} ({', '.join(cmd.aliases)})"
        await session.send(f"{label.ljust(26)} - {doc.splitlines()[0]}")
