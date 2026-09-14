"""In-game staff commands for players whose account has staff power (sage.services.staff_powers).

goto, at, where, stat, transfer, restore, mute, unmute and staff. To anyone without staff power
they answer exactly like an unknown command, and they never appear in help or autocomplete.
Every use by staff is written to the admin audit log with the staff account's name.
"""

from __future__ import annotations

from typing import Any

from sage.commands.registry import command
from sage.lexicon import t
from sage.network.session import Session


async def _authorise(session: Session, verb: str) -> tuple[Any, Any] | None:
    """(server, staff context) when this session may use ``verb``; otherwise answer and None."""
    from sage.app import app_instance
    from sage.services.staff_powers import may_use, staff_context

    ctx = await staff_context(app_instance, session) if session.player_id else None
    if ctx is None:
        await session.say("parser.unknown_command", verb=verb, hint="")
        return None
    if not may_use(ctx, verb):
        await session.say("staffcmd.tool_denied", verb=verb)
        return None
    return app_instance, ctx


async def _record(server: Any, ctx: Any, verb: str, target: str, **detail: Any) -> None:
    from sage.admin import audit

    await audit.record(server, ctx, f"ingame.{verb}", target, **detail)


def _words(session: Session, args: list[str]) -> list[str]:
    raw = getattr(session, "raw_args", None)
    return raw.split() if raw else list(args)


async def _character(server: Any, name: str) -> tuple[int, str] | None:
    """(character id, exact name) for a character name, connected or not (case-insensitive)."""
    from sqlalchemy import func, select

    from sage.state.models import Character

    wanted = (name or "").strip().lower()
    if not wanted:
        return None
    online = [n for n in server.session_manager.player_to_session if n.lower() == wanted]
    lookup = online[0] if online else wanted
    async with server.db.session_factory() as db:
        row = (
            await db.execute(
                select(Character.id, Character.name).where(
                    func.lower(Character.name) == lookup.lower()
                )
            )
        ).first()
    return (row[0], row[1]) if row else None


async def _split_name(server: Any, words: list[str]) -> tuple[tuple[int, str] | None, list[str]]:
    """Longest leading run of words that names a character (names may contain spaces)."""
    for k in range(min(len(words), 4), 0, -1):
        found = await _character(server, " ".join(words[:k]))
        if found:
            return found, words[k:]
    return None, words


async def _room_of(server: Any, target: str) -> str | None:
    """A room id for a room id or a character name (the room the character is in)."""
    if ":" in target and server.content_loader.get_room(target) is not None:
        return target
    found = await _character(server, target)
    if found is None:
        return None
    return await server.redis.get_player_location(found[1])


async def _announce(server: Any, room_id: str, mover: str, line: str) -> None:
    for other in await server.redis.get_room_players(room_id):
        if other == mover:
            continue
        target = server.session_manager.get_session_by_player(other)
        if target is not None and not getattr(target, "virtual", False):
            await target.send(line)


@command("goto", staff_only=True)
async def goto(session: Session, args: list[str]):
    """Go straight to a room or to a character. Usage: goto <zone:room | character>"""
    auth = await _authorise(session, "goto")
    if auth is None:
        return
    server, ctx = auth
    target = " ".join(_words(session, args)).strip()
    if not target:
        await session.say("staffcmd.goto_usage")
        return
    room_id = await _room_of(server, target)
    if room_id is None:
        await session.say("staffcmd.not_found", target=target)
        return
    if not ctx.may_read_zone(room_id.split(":", 1)[0]):
        await session.say("staffcmd.zone_denied", room=room_id)
        return
    here = await server.redis.get_player_location(session.player_id)
    if here:
        await _announce(
            server, here, session.player_id, t("staffcmd.vanishes", name=session.player_id)
        )
    await server.redis.set_player_location(session.player_id, room_id)
    await _announce(
        server, room_id, session.player_id, t("staffcmd.appears", name=session.player_id)
    )
    await _record(server, ctx, "goto", room_id, character=session.player_id, from_room=here)
    await server.dispatcher.dispatch(session, "look")


@command("at", staff_only=True)
async def at(session: Session, args: list[str]):
    """Run one command as if you stood somewhere else. Usage: at <zone:room | character> <command>"""
    auth = await _authorise(session, "at")
    if auth is None:
        return
    server, ctx = auth
    words = _words(session, args)
    if len(words) < 2:
        await session.say("staffcmd.at_usage")
        return
    if ":" in words[0]:
        room_id, rest = words[0], words[1:]
        room_id = room_id if server.content_loader.get_room(room_id) else None
    else:
        found, rest = await _split_name(server, words)
        room_id = await server.redis.get_player_location(found[1]) if found else None
    if room_id is None or not rest:
        await session.say("staffcmd.not_found", target=words[0])
        return
    if rest[0].lower() in ("at", "goto"):
        await session.say("staffcmd.at_usage")
        return
    if not ctx.may_read_zone(room_id.split(":", 1)[0]):
        await session.say("staffcmd.zone_denied", room=room_id)
        return
    here = await server.redis.get_player_location(session.player_id)
    # No arrival or departure lines: the staff member is only looking in for one command.
    await server.redis.set_player_location(session.player_id, room_id)
    try:
        await server.dispatcher.dispatch(session, " ".join(rest))
    finally:
        if here and await server.redis.get_player_location(session.player_id) == room_id:
            await server.redis.set_player_location(session.player_id, here)
    await _record(server, ctx, "at", room_id, character=session.player_id, command=" ".join(rest))


@command("where", staff_only=True)
async def where(session: Session, args: list[str]):
    """Who is where. Usage: where (everyone online) | where <character | item or creature template>"""
    auth = await _authorise(session, "where")
    if auth is None:
        return
    server, ctx = auth
    target = " ".join(_words(session, args)).strip()
    lines: list[str] = []
    if not target:
        for name in sorted(server.session_manager.player_to_session):
            live = server.session_manager.get_session_by_player(name)
            room = await server.redis.get_player_location(name)
            key = (
                "staffcmd.where_agent" if getattr(live, "virtual", False) else "staffcmd.where_row"
            )
            lines.append(t(key, name=name, room=room or "?"))
        await session.send("\r\n".join([t("staffcmd.where_header", count=len(lines)), *lines]))
        return
    found = await _character(server, target)
    if found is not None:
        room = await server.redis.get_player_location(found[1])
        online = server.session_manager.get_session_by_player(found[1]) is not None
        await session.say(
            "staffcmd.where_character",
            name=found[1],
            room=room or "?",
            state=t("staffcmd.online") if online else t("staffcmd.offline"),
        )
        return
    from sage.admin import references

    kind = "items" if server.content_loader.get_item_template(target) else None
    kind = kind or ("entities" if server.content_loader.get_entity_template(target) else None)
    if kind is None:
        await session.say("staffcmd.not_found", target=target)
        return
    live = await references.live_references(server, kind, target)
    if kind == "items":
        rows = [(r["room_id"], r["count"]) for r in live["on_floors"]]
        carriers = [r["name"] for r in live["carried_by"]["rows"]]
    else:
        rows = [(r["room_id"], r["count"]) for r in live["alive"]]
        carriers = []
    lines = [t("staffcmd.where_copies", room=room, count=count) for room, count in rows]
    if carriers:
        lines.append(t("staffcmd.where_carried", names=", ".join(carriers)))
    if not lines:
        lines.append(t("staffcmd.where_none", target=target))
    await session.send("\r\n".join([t("staffcmd.where_template", target=target), *lines]))


@command("stat", staff_only=True)
async def stat(session: Session, args: list[str]):
    """Look up a character, room or template. Usage: stat <character | zone:room | template>"""
    auth = await _authorise(session, "stat")
    if auth is None:
        return
    server, ctx = auth
    target = " ".join(_words(session, args)).strip()
    if not target:
        await session.say("staffcmd.stat_usage")
        return
    found = await _character(server, target)
    if found is not None:
        from sage.admin import character_tools

        d = await character_tools.detail(server, found[0])
        vitals = ", ".join(f"{v['label']} {v['value']}/{v['max']}" for v in d.get("vitals", []))
        money = ", ".join(f"{c['name']} {c['balance']}" for c in d["currencies"])
        lines = [
            t("staffcmd.stat_character", name=d["name"], account=d["account"], room=d["room_id"]),
            t(
                "staffcmd.stat_state",
                state=t("staffcmd.online") if d["online"] else t("staffcmd.offline"),
                suspended=t("staffcmd.suspended") if d["suspended"] else "",
            ),
            t("staffcmd.stat_vitals", vitals=vitals or "-", money=money or "-"),
            t(
                "staffcmd.stat_inventory",
                count=len(d["inventory"]),
                items=", ".join(
                    (i.get("name") or i.get("template") or "?") for i in d["inventory"][:10]
                )
                or "-",
            ),
        ]
        await session.send("\r\n".join(lines))
        return
    room = server.content_loader.get_room(target) if ":" in target else None
    if room is not None:
        present = sorted(await server.redis.get_room_players(target))
        exits = ", ".join(sorted(room.exits)) or "-"
        await session.send(
            "\r\n".join(
                [
                    t("staffcmd.stat_room", room=target, name=room.name or target),
                    t("staffcmd.stat_room_detail", exits=exits, present=", ".join(present) or "-"),
                ]
            )
        )
        return
    template = server.content_loader.get_item_template(
        target
    ) or server.content_loader.get_entity_template(target)
    if template is not None:
        fields = template.model_dump(exclude_none=True)
        shown = ", ".join(
            f"{k}={v}"
            for k, v in fields.items()
            if k not in ("id", "description") and not isinstance(v, dict | list)
        )
        await session.say("staffcmd.stat_template", id=target, fields=shown or "-")
        return
    await session.say("staffcmd.not_found", target=target)


@command("transfer", staff_only=True)
async def transfer(session: Session, args: list[str]):
    """Bring a character to you, or send them to a room. Usage: transfer <character> [zone:room]"""
    auth = await _authorise(session, "transfer")
    if auth is None:
        return
    server, ctx = auth
    found, rest = await _split_name(server, _words(session, args))
    if found is None:
        await session.say("staffcmd.transfer_usage")
        return
    room_id = rest[0] if rest else await server.redis.get_player_location(session.player_id)
    if not room_id or server.content_loader.get_room(room_id) is None:
        await session.say("staffcmd.not_found", target=room_id or "?")
        return
    if not ctx.may_write_zone(room_id.split(":", 1)[0]):
        await session.say("staffcmd.zone_denied", room=room_id)
        return
    from sage.admin import character_tools

    await character_tools.move(server, found[0], room_id, by=ctx.username)
    await session.say("staffcmd.transferred", name=found[1], room=room_id)
    await _record(
        server, ctx, "transfer", found[1], room_id=room_id, by_character=session.player_id
    )


@command("restore", staff_only=True)
async def restore(session: Session, args: list[str]):
    """Fill a character's vitals. Usage: restore <character | me>"""
    auth = await _authorise(session, "restore")
    if auth is None:
        return
    server, ctx = auth
    target = " ".join(_words(session, args)).strip() or "me"
    found = await _character(server, session.player_id if target.lower() == "me" else target)
    if found is None:
        await session.say("staffcmd.not_found", target=target)
        return
    from sage.admin import character_tools

    result = await character_tools.restore_vitals(server, found[0], by=ctx.username)
    key = "staffcmd.restored" if result["changed"] else "staffcmd.nothing_to_restore"
    await session.say(key, name=found[1])
    await _record(server, ctx, "restore", found[1], changed=result["changed"])


async def _account_of(server: Any, character_id: int) -> int:
    from sage.state.models import Character

    async with server.db.session_factory() as db:
        return (await db.get(Character, character_id)).account_id


@command("mute", staff_only=True)
async def mute(session: Session, args: list[str]):
    """Stop a player talking for a while. Usage: mute <character> <minutes> [reason]"""
    auth = await _authorise(session, "mute")
    if auth is None:
        return
    server, ctx = auth
    found, rest = await _split_name(server, _words(session, args))
    if found is None or not rest or not rest[0].isdigit() or not 1 <= int(rest[0]) <= 525_600:
        await session.say("staffcmd.mute_usage")
        return
    from sage.services.moderation import set_mute

    minutes, reason = int(rest[0]), " ".join(rest[1:])
    account_id = await _account_of(server, found[0])
    # A mute is on the account, so a character of the staff member's own account counts as them.
    if account_id == getattr(session, "account_id", None):
        await session.say("staffcmd.not_yourself")
        return
    await set_mute(server, account_id, minutes, reason)
    await session.say("staffcmd.muted", name=found[1], minutes=minutes)
    await _record(
        server,
        ctx,
        "mute",
        f"account:{account_id}",
        character=found[1],
        minutes=minutes,
        reason=reason,
    )


@command("unmute", staff_only=True)
async def unmute(session: Session, args: list[str]):
    """Let a muted player talk again. Usage: unmute <character>"""
    auth = await _authorise(session, "unmute")
    if auth is None:
        return
    server, ctx = auth
    found, _ = await _split_name(server, _words(session, args))
    if found is None:
        await session.say("staffcmd.unmute_usage")
        return
    from sage.services.moderation import set_mute

    account_id = await _account_of(server, found[0])
    await set_mute(server, account_id, None)
    await session.say("staffcmd.unmuted", name=found[1])
    await _record(server, ctx, "unmute", f"account:{account_id}", character=found[1])


@command("staff", aliases=["wizhelp"], staff_only=True)
async def staff(session: Session, args: list[str]):
    """List the staff commands you may use. Usage: staff"""
    auth = await _authorise(session, "staff")
    if auth is None:
        return
    _, ctx = auth
    from sage.commands.registry import registry
    from sage.services.staff_powers import COMMAND_TOOLS, may_use

    lines = [t("staffcmd.list_header", role=ctx.role)]
    for verb in sorted(COMMAND_TOOLS):
        cmd = registry.get(verb)
        if cmd is None or not may_use(ctx, verb):
            continue
        summary = (cmd.handler.__doc__ or "").strip().splitlines()[0]
        lines.append(t("staffcmd.list_row", verb=verb.ljust(9), summary=summary))
    await session.send("\r\n".join(lines))
