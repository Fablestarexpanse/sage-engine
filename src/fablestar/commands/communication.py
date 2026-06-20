"""Communication commands — say (room broadcast) and similar player-to-player messages."""

from fablestar.commands.registry import command
from fablestar.network.session import Session


@command("say")
async def say(session: Session, args: list[str]):
    """Speak to everyone in your current room."""
    if not args:
        await session.send("Say what?")
        return

    message = " ".join(args)
    from fablestar.__main__ import app_instance

    room_id = await app_instance.redis.get_player_location(session.player_id or "test_player")
    if not room_id:
        await session.send("You can't speak in the void.")
        return

    player_name = session.player_id or "Guest"
    broadcast_msg = f'{player_name} says: "{message}"'

    # Send to self
    await session.send(f'You say: "{message}"')

    # Broadcast to room (not implemented yet in session_manager, but we can iterate)
    room_players = await app_instance.redis.get_room_players(room_id)
    for target_pid in room_players:
        if target_pid != (session.player_id or "test_player"):
            target_session = app_instance.session_manager.get_session_by_player(target_pid)
            if target_session:
                await target_session.send(broadcast_msg)
