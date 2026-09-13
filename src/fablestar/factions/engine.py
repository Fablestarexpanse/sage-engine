"""
Faction reputation bookkeeping — pure functions over the player stats blob.

Reputation lives at stats["factions"] = {faction_id: int}, so it rides the
existing persistence flush like counters and effects do. Standing changes
return player-facing messages; only standing-level crossings are announced
(a silent +2 shouldn't spam the feed).
"""

from typing import Any

from fablestar.factions.models import REP_MAX, REP_MIN, FactionModel, standing_name
from fablestar.factions.registry import FactionRegistry

FACTIONS_KEY = "factions"


def ensure_factions(stats: dict[str, Any]) -> dict[str, int]:
    if not isinstance(stats.get(FACTIONS_KEY), dict):
        stats[FACTIONS_KEY] = {}
    return stats[FACTIONS_KEY]


def get_rep(stats: dict[str, Any], faction: FactionModel) -> int:
    reps = ensure_factions(stats)
    if faction.id not in reps:
        return faction.initial_rep
    return int(reps[faction.id])


def adjust_rep(stats: dict[str, Any], faction: FactionModel, delta: int) -> str | None:
    """Apply a rep change; return an announcement when the standing level changes."""
    if delta == 0:
        return None
    reps = ensure_factions(stats)
    before = get_rep(stats, faction)
    after = max(REP_MIN, min(REP_MAX, before + delta))
    reps[faction.id] = after
    old_level, new_level = standing_name(before), standing_name(after)
    if new_level == old_level:
        return None
    direction = "improves" if after > before else "worsens"
    return f"Your standing with {faction.name} {direction}: you are now {new_level}."


def apply_kill_reputation(
    stats: dict[str, Any],
    registry: FactionRegistry,
    template_id: str,
    entity_faction: str,
) -> list[str]:
    """
    Rep consequences of killing one entity. The template's own faction (if
    defined in content) penalises the killer; factions listing the template
    as an enemy reward the kill.
    """
    messages: list[str] = []
    own = registry.get(entity_faction) if entity_faction else None
    if own is not None:
        msg = adjust_rep(stats, own, own.kill_rep)
        if msg:
            messages.append(msg)
    for faction in registry.enemies_of_template(template_id):
        if own is not None and faction.id == own.id:
            continue
        msg = adjust_rep(stats, faction, faction.enemy_kill_rep)
        if msg:
            messages.append(msg)
    return messages


def standings_lines(stats: dict[str, Any], registry: FactionRegistry) -> list[str]:
    """Lines for the 'factions' command — every known faction with rep + standing."""
    lines = []
    for faction in registry.all():
        rep = get_rep(stats, faction)
        lines.append(f"  {faction.name}: {standing_name(rep)} ({rep:+d}) — {faction.description}")
    return lines
