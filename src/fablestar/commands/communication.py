"""Communication commands — say (room broadcast) and similar player-to-player messages."""

from fablestar.commands.registry import command
from fablestar.network.session import Session


@command("say")
async def say(session: Session, args: list[str]):
    """Speak to everyone in your current room."""
    if not args:
        await session.send("Say what?")
        return

    if not session.player_id:
        await session.send("Not authenticated.")
        return

    message = " ".join(args)
    from fablestar.app import app_instance

    room_id = await app_instance.redis.get_player_location(session.player_id)
    if not room_id:
        await session.send("You can't speak in the void.")
        return

    player_name = session.player_id
    broadcast_msg = f'{player_name} says: "{message}"'

    # Send to self
    await session.send(f'You say: "{message}"')

    # Broadcast to room
    room_players = await app_instance.redis.get_room_players(room_id)
    for target_pid in room_players:
        if target_pid != session.player_id:
            target_session = app_instance.session_manager.get_session_by_player(target_pid)
            if target_session:
                await target_session.send(broadcast_msg)


@command("emote", aliases=["me"])
async def emote(session: Session, args: list[str]):
    """Perform an action everyone in the room can see. Usage: emote <does something>"""
    if not args:
        await session.send("Emote what? Usage: emote <does something>")
        return
    if not session.player_id:
        await session.send("Not authenticated.")
        return

    from fablestar.app import app_instance

    room_id = await app_instance.redis.get_player_location(session.player_id)
    if not room_id:
        await session.send("There is nobody here to see it.")
        return
    line = f"{session.player_id} {' '.join(args)}"
    await session.send(line)
    for target_pid in await app_instance.redis.get_room_players(room_id):
        if target_pid != session.player_id:
            target_session = app_instance.session_manager.get_session_by_player(target_pid)
            if target_session:
                await target_session.send(line)


@command("tell", aliases=["whisper", "t"])
async def tell(session: Session, args: list[str]):
    """Send a private message to an online player. Usage: tell <player> <message>"""
    if len(args) < 2:
        await session.send("Tell whom what? Usage: tell <player> <message>")
        return
    if not session.player_id:
        await session.send("Not authenticated.")
        return

    from fablestar.app import app_instance

    needle = args[0].lower()
    target_pid = next(
        (
            pid
            for pid in app_instance.session_manager.player_to_session
            if pid.lower() == needle or pid.lower().startswith(needle)
        ),
        None,
    )
    if target_pid is None:
        await session.send(f"No one called '{args[0]}' is online.")
        return
    if target_pid == session.player_id:
        await session.send("You mutter to yourself. It doesn't help.")
        return
    target_session = app_instance.session_manager.get_session_by_player(target_pid)
    if target_session is None:
        await session.send(f"No one called '{args[0]}' is online.")
        return
    message = " ".join(args[1:])
    await session.send(f'You tell {target_pid}: "{message}"')
    await target_session.send(f'{session.player_id} tells you: "{message}"')


@command("who", aliases=["online"])
async def who(session: Session, args: list[str]):
    """List who is online. Usage: who"""
    from fablestar.app import app_instance

    names = sorted(app_instance.session_manager.player_to_session)
    if not names:
        await session.send("The station is silent. Nobody is connected.")
        return
    await session.send("\r\n".join([f"Online ({len(names)}):", *[f"  {name}" for name in names]]))
