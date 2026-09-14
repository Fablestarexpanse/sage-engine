"""Factions command — show standing with every known faction."""

from sage.commands.registry import command
from sage.network.session import Session


@command("factions", aliases=["rep", "reputation"])
async def factions(session: Session, args: list[str]):
    """Show your faction standings. Usage: factions"""
    from sage.app import app_instance
    from sage.factions.engine import standings_lines

    player_id = session.player_id
    if not player_id:
        await session.send("Not authenticated.")
        return

    registry = app_instance.content_loader.get_faction_registry()
    if not registry.all():
        await session.send("No factions have taken notice of you yet.")
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    await session.send("\r\n".join(["Faction standings:", *standings_lines(stats, registry)]))
