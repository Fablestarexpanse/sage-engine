"""Achievement commands — list earned achievements and browse what exists."""

from sage.commands.registry import command
from sage.network.session import Session


@command("achievements", aliases=["ach"])
async def achievements(session: Session, args: list[str]):
    """Show your achievements. Usage: achievements [all]"""
    from sage.achievements.engine import COUNTERS_KEY, GRANTS_KEY
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        await session.send("Not authenticated.")
        return

    registry = app_instance.content_loader.get_achievement_registry()
    stats = await app_instance.redis.get_player_stats(player_id)
    grants = stats.get(GRANTS_KEY) if isinstance(stats.get(GRANTS_KEY), dict) else {}
    counters = stats.get(COUNTERS_KEY) if isinstance(stats.get(COUNTERS_KEY), dict) else {}

    if args and args[0] == "all":
        lines = ["All achievements:"]
        for ach in registry.all():
            mark = "[X]" if ach.id in grants else "[ ]"
            progress = ", ".join(
                f"{c}: {min(int(counters.get(c, 0)), t)}/{t}" for c, t in ach.criteria.items()
            )
            lines.append(f"  {mark} ({ach.level}) {ach.name} — {ach.instructions} ({progress})")
        await session.send("\r\n".join(lines))
        return

    earned = [a for a in registry.all() if a.id in grants]
    if not earned:
        await session.send("No achievements yet. Try 'achievements all' to see what's out there.")
        return
    lines = [f"Achievements ({len(earned)}/{len(registry.all())}):"]
    lines += [f"  ({a.level}) {a.story_line()}" for a in earned]
    await session.send("\r\n".join(lines))
