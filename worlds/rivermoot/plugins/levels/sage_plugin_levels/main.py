"""Levels: experience from kills and a new level every `xp_per_level` points."""

from __future__ import annotations

from typing import Any

from sage.api import EntityKilled, PluginAPI

BLOCK = "levels"


def fresh() -> dict[str, int]:
    return {"level": 1, "xp": 0}


def add_xp(block: dict[str, Any], amount: int, per_level: int) -> list[int]:
    """Add experience in place; return every level reached (usually empty or one)."""
    block["xp"] = int(block.get("xp", 0)) + amount
    block["level"] = int(block.get("level", 1))
    reached = []
    while block["xp"] >= block["level"] * per_level:
        block["xp"] -= block["level"] * per_level
        block["level"] += 1
        reached.append(block["level"])
    return reached


def setup(api: PluginAPI) -> None:
    api.state.block(BLOCK, default=fresh)
    per_kill = int(api.param("xp_per_kill", 5))
    per_level = int(api.param("xp_per_level", 10))

    def on_kill(event: EntityKilled) -> None:
        # event.stats is the killer's stats blob, saved by combat right after this event.
        block = event.stats.setdefault(BLOCK, fresh())
        reached = add_xp(block, per_kill, per_level)
        event.messages.append(api.t("levels.gain", xp=per_kill))
        for level in reached:
            event.messages.append(api.t("levels.level_up", level=level))

    async def level(session, args) -> None:
        """Show your level and experience. Usage: level"""
        block = await api.state.get(session.player_id, BLOCK)
        needed = int(block.get("level", 1)) * per_level
        await session.send(
            api.t(
                "levels.status", level=block.get("level", 1), xp=block.get("xp", 0), needed=needed
            )
        )

    api.events.subscribe(EntityKilled, on_kill)
    api.commands.register("level", level, aliases=["lvl"])
