"""Movement commands — cardinal and vertical directions, all delegating to move_to()."""

import logging

from sage.commands.registry import command
from sage.network.session import Session

logger = logging.getLogger(__name__)


OPPOSITE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "below",
    "down": "above",
    "northeast": "southwest",
    "southwest": "northeast",
    "northwest": "southeast",
    "southeast": "northwest",
}


async def _announce(app_instance, room_id: str, mover: str, line: str) -> None:
    """Tell everyone else in a room that someone came or went."""
    for other in await app_instance.redis.get_room_players(room_id):
        if other == mover:
            continue
        target = app_instance.session_manager.get_session_by_player(other)
        # Agents already see occupants in every look; movement chatter would
        # crowd conversation out of their short perception window.
        if target is not None and not getattr(target, "is_agent", False):
            try:
                await target.send(line)
            except Exception:
                logger.debug("movement announce failed for %s", other, exc_info=True)


def move_to(direction: str):
    """Helper to create a movement command for a specific direction."""

    async def _direction_handler(session: Session, args: list[str]):
        from sage.app import app_instance

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

        # 3. Update location, telling both rooms
        await _announce(app_instance, room_id, player_id, f"{player_id} leaves {direction}.")
        await app_instance.redis.set_player_location(player_id, target_room_id)
        from sage.core.events import RoomEntered, emit

        await emit(
            app_instance,
            RoomEntered(
                player_id=player_id,
                room_id=target_room_id,
                from_room_id=room_id,
                direction=direction,
            ),
        )
        arrival = OPPOSITE.get(direction)
        await _announce(
            app_instance,
            target_room_id,
            player_id,
            f"{player_id} arrives from the {arrival}." if arrival else f"{player_id} arrives.",
        )

        # Traversal gain rewards exploring, not pacing: a first visit teaches a
        # lot; familiar ground teaches less the better you already are. (Flat
        # 12% per step gave agents 66-153 pathfinding levels overnight.)
        from sage.proficiencies.field_gain import try_field_gain_for_player

        try:
            mover_stats = await app_instance.redis.get_player_stats(player_id)
            first_visit = target_room_id not in (mover_stats.get("visited_rooms") or [])
            path_lvl = int(
                ((mover_stats.get("conduit") or {}).get("proficiencies") or {})
                .get("traversal.navigation.pathfinding", {})
                .get("level", 0)
            )
        except Exception:
            first_visit, path_lvl = False, 0
        gain_chance = 0.6 if first_visit else 0.04 / (1 + path_lvl / 5)
        await try_field_gain_for_player(
            player_id, "traversal.navigation.pathfinding", chance=gain_chance
        )

        # Unique-room exploration counter (best-effort, writes only on first visit).
        from sage.achievements.engine import announcement, record_room_visit_for_player

        granted = await record_room_visit_for_player(player_id, target_room_id)

        # Room hazards roll against the player on entry (best-effort).
        hazard_messages: list[str] = []
        target_room = app_instance.content_loader.get_room(target_room_id)
        if target_room and target_room.hazards:
            try:
                from sage.effects.hazards import HAZARD_RESIST_LEAF, apply_room_hazards

                stats = await app_instance.redis.get_player_stats(player_id)
                hazard_messages = apply_room_hazards(stats, target_room)
                await app_instance.redis.set_player_stats(player_id, stats)
                await try_field_gain_for_player(player_id, HAZARD_RESIST_LEAF, chance=0.15)
            except Exception as exc:
                logger.warning("Hazard application skipped: %s", exc)

        # 4. Describe new room
        await session.send(f"You move {direction}.")
        session.look_narrate = first_visit
        await app_instance.dispatcher.dispatch(session, "look")
        for msg in hazard_messages:
            await session.send(f"\r\n{msg}")
        for ach in granted:
            await session.send(f"\r\n{announcement(ach)}")

    return _direction_handler


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
