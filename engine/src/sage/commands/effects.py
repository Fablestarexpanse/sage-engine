"""Effects command — show active buffs and debuffs."""

from sage.commands.registry import command
from sage.network.session import Session


@command("effects", aliases=["buffs", "debuffs"])
async def effects(session: Session, args: list[str]):
    """Show active effects on you. Usage: effects"""
    from sage.app import app_instance
    from sage.effects.engine import describe_effects

    player_id = session.player_id
    if not player_id:
        await session.send("Not authenticated.")
        return

    stats = await app_instance.redis.get_player_stats(player_id)
    lines = describe_effects(stats)
    if not lines:
        await session.send("Nothing ails or aids you.")
        return
    await session.send("\r\n".join(["Active effects:", *lines]))


@command("rest", aliases=["sleep", "recover"])
async def rest(session: Session, args: list[str]):
    """Rest to recover health — only somewhere safe. Usage: rest"""
    from sage.app import app_instance
    from sage.effects.engine import apply_effect, find_effects, make_effect

    player_id = session.player_id
    if not player_id:
        await session.send("Not authenticated.")
        return

    room_id = await app_instance.redis.get_player_location(player_id)
    room = app_instance.content_loader.get_room(room_id) if room_id else None
    if room is None or room.type != "safe":
        await session.send("Too dangerous to rest here. Find somewhere safe — the clinic, say.")
        return

    stats = await app_instance.redis.get_player_stats(player_id)
    if int(stats.get("hp", 0)) >= int(stats.get("max_hp", stats.get("hp", 1))):
        await session.send("You are already in one piece.")
        return
    if find_effects(stats, "body.resting"):
        await session.send("You are already resting. Give it a moment.")
        return

    apply_effect(
        stats,
        make_effect(
            "body.resting",
            name="resting",
            description="Your body knits itself back together.",
            kind="hot",
            magnitude=2,
            interval=5.0,
            duration=30.0,
            debuff=False,
        ),
    )
    await app_instance.redis.set_player_stats(player_id, stats)
    await session.send("You settle onto a diagnostic bed and let the station's hum take over.")
