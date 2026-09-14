"""Achievements plugin: counters (engine) reach thresholds -> grants and announcements."""

from __future__ import annotations

import time
from typing import Any

from sage.api import CountersChanged, PluginAPI

from .models import AchievementModel
from .registry import AchievementRegistry, load_achievements

GRANTS_KEY = "achievements"
COUNTERS_KEY = "counters"


def met(ach: AchievementModel, counters: dict[str, Any]) -> bool:
    checks = (int(counters.get(c, 0)) >= threshold for c, threshold in ach.criteria.items())
    return any(checks) if ach.match == "any" else all(checks)


def check_grants(
    stats: dict[str, Any], registry: AchievementRegistry, changed: list[str], now: int | None = None
) -> list[AchievementModel]:
    """Grant every not-yet-granted achievement watching a changed counter whose criteria hold."""
    grants = stats.get(GRANTS_KEY)
    if not isinstance(grants, dict):
        grants = stats[GRANTS_KEY] = {}
    counters = stats.get(COUNTERS_KEY) if isinstance(stats.get(COUNTERS_KEY), dict) else {}
    granted: list[AchievementModel] = []
    seen: set[str] = set()
    for counter in changed:
        for ach in registry.watching(counter):
            if ach.id in grants or ach.id in seen:
                continue
            seen.add(ach.id)
            if met(ach, counters):
                grants[ach.id] = {"granted_at": now if now is not None else int(time.time())}
                granted.append(ach)
    return granted


def setup(api: PluginAPI) -> None:
    api.state.block(GRANTS_KEY)
    cache = api.content.cached("achievements", lambda d: load_achievements(d.parent))

    def announce(ach: AchievementModel) -> str:
        return api.t("achievements.unlocked", level=ach.level, story=ach.story_line())

    def on_counters(event: CountersChanged) -> None:
        for ach in check_grants(event.stats, cache.get(), event.counters):
            event.messages.append(announce(ach))

    async def achievements(session, args) -> None:
        """Show your achievements. Usage: achievements [all]"""
        registry = cache.get()
        stats = await api.state.snapshot(session.player_id)
        counters = stats.get(COUNTERS_KEY) if isinstance(stats.get(COUNTERS_KEY), dict) else {}
        grants = await api.state.get(session.player_id, GRANTS_KEY)
        if args and args[0] == "all":
            lines = [api.t("achievements.all_header")]
            for ach in registry.all():
                progress = ", ".join(
                    f"{c}: {min(int(counters.get(c, 0)), t)}/{t}" for c, t in ach.criteria.items()
                )
                lines.append(
                    api.t(
                        "achievements.all_entry",
                        mark="[X]" if ach.id in grants else "[ ]",
                        level=ach.level,
                        name=ach.name,
                        instructions=ach.instructions,
                        progress=progress,
                    )
                )
            await session.send("\r\n".join(lines))
            return
        earned = [a for a in registry.all() if a.id in grants]
        if not earned:
            await session.send(api.t("achievements.none"))
            return
        lines = [api.t("achievements.header", earned=len(earned), total=len(registry.all()))]
        lines += [api.t("achievements.entry", level=a.level, story=a.story_line()) for a in earned]
        await session.send("\r\n".join(lines))

    api.events.subscribe(CountersChanged, on_counters)
    api.commands.register("achievements", achievements, aliases=["ach"])
