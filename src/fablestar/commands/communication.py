"""Communication commands — say (room broadcast) and similar player-to-player messages."""

import json
import time

from fablestar.commands.registry import command
from fablestar.network.session import Session


async def _chat_notice(target: Session, channel: str, sender: str, text: str, self_line: bool):
    """Structured copy of a chat line for the client Comms panel.

    Agents read plain perception lines; JSON notices are noise to them.
    """
    if getattr(target, "is_agent", False):
        return
    notice = {
        "client_notice": "chat_message",
        "channel": channel,  # "local" | "tell"
        "from": sender,
        "text": text,
        "self": self_line,
        "at": time.time(),
    }
    await target.send(json.dumps(notice) + "\r\n")


def _free_text(session: Session, args: list[str]) -> str:
    """The player's words with their original case (the tokenizer lowercases args)."""
    raw = getattr(session, "raw_args", None)
    return raw.strip() if raw else " ".join(args)


def resolve_tell_target(words: list[str], online: list[str], sender: str):
    """Split 'tell' words into (target, message) against online names.

    Longest exact name wins, then a unique name prefix. Returns
    (target, message, None) on success or (None, None, reason) where reason is
    'self', 'nobody' or a list of ambiguous names.
    """
    others = [n for n in online if n != sender]
    most = min(len(words) - 1, 5)
    for k in range(most, 0, -1):
        cand = " ".join(words[:k]).lower()
        exact = [n for n in others if n.lower() == cand]
        if exact:
            return exact[0], " ".join(words[k:]), None
        if cand == sender.lower():
            return None, None, "self"
    for k in range(most, 0, -1):
        cand = " ".join(words[:k]).lower()
        hits = [n for n in others if n.lower().startswith(cand)]
        if len(hits) == 1:
            return hits[0], " ".join(words[k:]), None
        if len(hits) > 1:
            return None, None, sorted(hits)
    if words and sender.lower().startswith(words[0].lower()):
        return None, None, "self"
    return None, None, "nobody"


@command("say")
async def say(session: Session, args: list[str]):
    """Speak to everyone in your current room."""
    if not args:
        await session.send("Say what?")
        return

    if not session.player_id:
        await session.send("Not authenticated.")
        return

    message = _free_text(session, args)
    from fablestar.app import app_instance

    room_id = await app_instance.redis.get_player_location(session.player_id)
    if not room_id:
        await session.send("You can't speak in the void.")
        return

    player_name = session.player_id
    broadcast_msg = f'{player_name} says: "{message}"'

    # Send to self
    await session.send(f'You say: "{message}"')
    await _chat_notice(session, "local", player_name, message, self_line=True)

    # Broadcast to room
    room_players = await app_instance.redis.get_room_players(room_id)
    for target_pid in room_players:
        if target_pid != session.player_id:
            target_session = app_instance.session_manager.get_session_by_player(target_pid)
            if target_session:
                await target_session.send(broadcast_msg)
                await _chat_notice(target_session, "local", player_name, message, self_line=False)


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
    line = f"{session.player_id} {_free_text(session, args)}"
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

    words = _free_text(session, args).split()
    online = list(app_instance.session_manager.player_to_session)
    target_pid, message, reason = resolve_tell_target(words, online, session.player_id)
    if reason == "self":
        await session.send("You mutter to yourself. It doesn't help.")
        return
    if isinstance(reason, list):
        await session.send(f"Which one? {', '.join(reason)}")
        return
    if target_pid is None:
        await session.send(f"No one called '{words[0]}' is online.")
        return
    if not message:
        await session.send(f"Tell {target_pid} what?")
        return
    target_session = app_instance.session_manager.get_session_by_player(target_pid)
    if target_session is None:
        await session.send(f"No one called '{args[0]}' is online.")
        return
    await session.send(f'You tell {target_pid}: "{message}"')
    await target_session.send(f'{session.player_id} tells you: "{message}"')
    await _chat_notice(session, "tell", f"→ {target_pid}", message, self_line=True)
    await _chat_notice(target_session, "tell", session.player_id, message, self_line=False)


@command("who", aliases=["online"])
async def who(session: Session, args: list[str]):
    """List who is online. Usage: who"""
    from fablestar.app import app_instance

    names = sorted(app_instance.session_manager.player_to_session)
    if not names:
        await session.send("The station is silent. Nobody is connected.")
        return
    await session.send("\r\n".join([f"Online ({len(names)}):", *[f"  {name}" for name in names]]))
