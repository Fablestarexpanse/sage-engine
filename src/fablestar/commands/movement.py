"""Movement commands — cardinal and vertical directions, all delegating to move_to()."""

import random

from fablestar.commands.registry import command
from fablestar.network.session import Session


def move_to(direction: str):
    """Helper to create a movement command for a specific direction."""

    async def mover(session: Session, args: list[str]):
        from fablestar.app import app_instance

        # 1. Get current room
        if not session.player_id:
            await session.send("Not authenticated.")
            return
        player_id = session.player_id
        room_id = await app_instance.redis.get_player_location(player_id)
        if not room_id:
            await session.send("You are lost in the void.")
            return

        room = app_instance.content_loader.get_room(room_id)
        if not room:
            await session.send("The world is collapsing around you.")
            return

        # 2. Check for exit
        if direction not in room.exits:
            await session.send(f"You cannot go {direction}.")
            return

        exit_meta = room.exits[direction]
        target_room_id = exit_meta.destination

        # 3. Update location
        await app_instance.redis.set_player_location(player_id, target_room_id)

        # Optional field gain: traversal (low chance per move to avoid spam).
        if random.random() < 0.12:
            try:
                from fablestar.proficiencies.engine import ProficiencyEngine
                from fablestar.proficiencies.state_helpers import ensure_proficiency_block

                stats = await app_instance.redis.get_player_stats(player_id)
                ensure_proficiency_block(stats)
                eng = ProficiencyEngine(app_instance.content_loader.get_proficiency_registry())
                eng.try_field_gain(
                    stats,
                    "traversal.navigation.pathfinding",
                    context={"vr": False},
                )
                await app_instance.redis.set_player_stats(player_id, stats)
            except Exception:
                pass

        # 4. Describe new room
        await session.send(f"You move {direction}.")
        await app_instance.dispatcher.dispatch(session, "look")

    return mover


# Register cardinal / vertical (single-letter aliases)
for direction, aliases in [
    ("north", ["n"]),
    ("south", ["s"]),
    ("east", ["e"]),
    ("west", ["w"]),
    ("up", ["u"]),
    ("down", ["d"]),
]:
    handler = move_to(direction)
    handler.__doc__ = f"Move {direction}."
    command(direction, aliases=aliases)(handler)

# Corner directions (two-letter aliases; "n" stays north only)
for direction, aliases in [
    ("northeast", ["ne"]),
    ("northwest", ["nw"]),
    ("southeast", ["se"]),
    ("southwest", ["sw"]),
]:
    handler = move_to(direction)
    handler.__doc__ = f"Move {direction}."
    command(direction, aliases=aliases)(handler)
