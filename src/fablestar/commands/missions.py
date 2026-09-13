"""Mission commands — generated faction contracts (kill / collect)."""

import logging

from fablestar.commands.registry import command
from fablestar.network.session import Session

logger = logging.getLogger(__name__)


@command("missions", aliases=["mission"])
async def missions(session: Session, args: list[str]):
    """Faction contracts. Usage: missions [accept <faction> | complete | abandon]"""
    from fablestar.app import app_instance
    from fablestar.factions.missions import (
        MISSION_KEY,
        active_mission,
        describe_mission,
        generate_mission,
        try_complete_collect,
        will_deal,
    )

    player_id = session.player_id
    if not player_id:
        await session.send("Not authenticated.")
        return

    registry = app_instance.content_loader.get_faction_registry()
    stats = await app_instance.redis.get_player_stats(player_id)
    sub = args[0] if args else ""

    if sub == "accept":
        if active_mission(stats):
            await session.send("Finish or abandon your current mission first.")
            return
        needle = " ".join(args[1:]).lower()
        faction = next(
            (
                f
                for f in registry.all()
                if f.offers_missions() and (needle in f.id.lower() or needle in f.name.lower())
            ),
            None,
        )
        if not needle or faction is None:
            await session.send("Accept from whom? Usage: missions accept <faction>")
            return
        if not will_deal(stats, faction):
            await session.send(f"{faction.name} wants nothing to do with you.")
            return
        mission = generate_mission(faction)
        if mission is None:
            await session.send(f"{faction.name} has no work right now.")
            return
        stats[MISSION_KEY] = mission
        await app_instance.redis.set_player_stats(player_id, stats)
        await session.send(f"Contract accepted. {describe_mission(mission, registry)}")
        return

    if sub == "abandon":
        if not active_mission(stats):
            await session.send("You have no active mission.")
            return
        stats[MISSION_KEY] = None
        await app_instance.redis.set_player_stats(player_id, stats)
        await session.send("Contract abandoned. Nobody is impressed.")
        return

    if sub == "complete":
        inventory = await app_instance.redis.get_player_inventory(player_id)
        messages, new_inventory = try_complete_collect(stats, registry, inventory)
        if new_inventory is not None:
            await app_instance.redis.set_player_inventory(player_id, new_inventory)
            try:
                from fablestar.achievements.engine import announcement, record_counter

                ach_registry = app_instance.content_loader.get_achievement_registry()
                for ach in record_counter(stats, ach_registry, "missions_completed"):
                    messages.append(announcement(ach))
            except Exception as exc:
                logger.warning("Mission achievement counter skipped: %s", exc)
            await app_instance.redis.set_player_stats(player_id, stats)
        await session.send("\r\n".join(messages))
        return

    # Default view: active mission + who is hiring.
    lines = []
    mission = active_mission(stats)
    if mission:
        lines.append(f"Active — {describe_mission(mission, registry)}")
        if mission.get("kind") == "collect":
            lines.append("  Deliver with: missions complete")
    else:
        lines.append("No active mission.")
    hiring = [f for f in registry.all() if f.offers_missions() and will_deal(stats, f)]
    if hiring:
        lines.append("Hiring: " + ", ".join(f.name for f in hiring))
        lines.append("  Take a contract with: missions accept <faction>")
    await session.send("\r\n".join(lines))
