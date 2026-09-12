"""Effects command — show active buffs and debuffs."""

from fablestar.commands.registry import command
from fablestar.network.session import Session


@command("effects", aliases=["buffs", "debuffs"])
async def effects(session: Session, args: list[str]):
    """Show active effects on you. Usage: effects"""
    from fablestar.app import app_instance
    from fablestar.effects.engine import describe_effects

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
