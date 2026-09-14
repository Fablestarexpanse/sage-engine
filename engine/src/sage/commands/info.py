"""Info commands — look (with optional LLM narration) and help."""

import logging

from sage.commands.registry import command
from sage.lexicon import t
from sage.llm.observation import build_room_fact_block
from sage.llm.validation import LLMValidator
from sage.network.session import Session

logger = logging.getLogger(__name__)


@command("look", aliases=["l"])
async def look(session: Session, args: list[str]):
    """Look at the current room or an object."""
    from sage.app import app_instance

    if not session.player_id:
        await session.say("session.not_authenticated")
        return
    if args:
        from sage.commands.items import examine

        await examine(session, args)
        return
    # Movement's auto-look sets this False on familiar ground; typed looks narrate.
    narrate = getattr(session, "look_narrate", True)
    session.look_narrate = True
    room_id = await app_instance.redis.get_player_location(session.player_id)
    if not room_id:
        await session.say("void.lost")
        return

    room = app_instance.content_loader.get_room(room_id)
    if room:
        if room.name:
            await session.say("look.header", name=room.name, id=room.id)
        else:
            await session.say("look.header_unnamed", id=room.id)

        # Deterministic description immediately — the LLM must never make a
        # player wait to see the room. Narration arrives after, labeled, so a
        # late line can't masquerade as the response to the next command.
        await session.send(room.description.get("base", ""))

        from sage.world.clock import day_phase

        observation_block = build_room_fact_block(room, {"time_of_day": day_phase()})
        viewer = session.player_id

        async def _narrate():
            try:
                prompt = app_instance.prompt_manager.render(
                    "narrate.room", observation_block=observation_block
                )
                narration = await app_instance.llm_client.generate_or_raise(prompt)
                rules = app_instance.prompt_manager.style.rules()
                clean = LLMValidator(rules).sanitize(narration)
                # A scene of a room the player already left reads as a lie.
                if await app_instance.redis.get_player_location(viewer) != room_id:
                    return
                if clean and clean.strip():
                    await session.say("look.scene", text=clean.strip())
            except Exception as e:
                logger.debug("Room narration skipped: %s", e)
            finally:
                session.scene_narration_pending = False

        # Agents parse facts, not prose; their constant looks would flood the
        # narration backend. One pending scene per player: extras are dropped.
        if (
            narrate
            and app_instance.prompt_manager.enabled("narrate.room")
            and not getattr(session, "virtual", False)
            and not getattr(session, "scene_narration_pending", False)
        ):
            import asyncio as _asyncio

            session.scene_narration_pending = True
            _asyncio.get_running_loop().create_task(_narrate())

        if room.exits:
            await session.say("look.exits", exits=", ".join(room.exits.keys()))

        # 4b. Other players and agents present (deterministic)
        room_players = await app_instance.redis.get_room_players(room_id)
        others = sorted(p for p in room_players if p != session.player_id)
        if others:
            await session.say("look.also_here", names=", ".join(others))

        # 5. Show live entities (deterministic — no LLM)
        entity_ids = await app_instance.redis.get_room_entities(room_id)
        alive = []
        for eid in entity_ids:
            state = await app_instance.redis.get_entity_state(eid)
            if state and state.get("alive", True):
                alive.append(state.get("name") or t("look.something"))
        if alive:
            await session.say("look.entities", names=", ".join(alive))

        # 6. Show floor items (deterministic)
        item_ids = await app_instance.redis.get_room_items(room_id)
        floor_items = []
        for iid in item_ids:
            istate = await app_instance.redis.get_item_state(iid)
            if istate:
                floor_items.append(istate.get("name") or t("look.something"))
        if floor_items:
            await session.say("look.floor_items", names=", ".join(floor_items))
    else:
        await session.say("void.nowhere")


@command("map", aliases=["chart"])
async def map_cmd(session: Session, args: list[str]):
    """Show the zone map: where you are and what you've explored. Usage: map"""
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        await session.say("map.nowhere")
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    visited = set(stats.get("visited_rooms") or [])
    data = app_instance._zone_map(room_id, visited)
    if not data:
        await session.say("map.no_chart")
        return
    lines = [t("map.zone", zone=data["zone"])]
    unexplored = 0
    for r in sorted(data["rooms"], key=lambda x: x["name"]):
        if r["id"] == data["current"]:
            lines.append(t("map.here", name=r["name"]))
        elif r["visited"]:
            lines.append(t("map.explored", name=r["name"]))
        else:
            unexplored += 1
    if unexplored:
        lines.append(t("map.unexplored", count=unexplored))
    lines.append(t("map.legend"))
    await session.send("\r\n".join(lines))


def _help_text(verb: str, handler) -> str:
    """help.<verb> from the lexicon, else the handler docstring."""
    from sage import lexicon

    return lexicon.active().get(f"help.{verb}") or (
        (handler.__doc__ or "").strip() or lexicon.t("help.no_description")
    )


@command("help", aliases=["h", "?"])
async def help_cmd(session: Session, args: list[str]):
    """Display available commands. Usage: help [command]"""
    from sage.commands.registry import registry

    if args:
        wanted = args[0].lower()
        cmd = registry.get(wanted)
        if cmd is None:
            await session.say("help.no_such_command", verb=wanted)
            return
        doc = _help_text(cmd.name, cmd.handler)
        aliases = t("help.entry_aliases", aliases=", ".join(cmd.aliases)) if cmd.aliases else ""
        await session.say("help.entry", verb=wanted, aliases=aliases, doc=doc)
        return

    await session.say("help.header")
    cmds = sorted(registry._commands.keys())
    for cmd_name in cmds:
        cmd = registry.get(cmd_name)
        if cmd is None:
            continue
        doc = _help_text(cmd_name, cmd.handler)
        label = (
            t("help.row_label", verb=cmd_name, aliases=", ".join(cmd.aliases))
            if cmd.aliases
            else cmd_name
        )
        await session.say("help.row", label=label.ljust(26), summary=doc.splitlines()[0])
