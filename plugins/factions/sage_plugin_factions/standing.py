"""
Faction reputation bookkeeping — pure functions over the character's stats blob.

Reputation lives in the ``factions`` state block ({faction_id: int}), so it rides the engine's
persistence flush. Standing changes return player-facing lines; only standing-level crossings are
announced (a silent +2 shouldn't spam the feed).
"""

from typing import Any

from sage.api import t

from .models import REP_MAX, REP_MIN, FactionModel, standing_name
from .registry import FactionRegistry

FACTIONS_KEY = "factions"


def standing_label(rep: int) -> str:
    return t(f"factions.standing.{standing_name(rep)}")


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
    if standing_name(after) == standing_name(before):
        return None
    key = "factions.standing_improves" if after > before else "factions.standing_worsens"
    return t(key, faction=faction.name, standing=standing_label(after))


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
        lines.append(
            t(
                "factions.entry",
                name=faction.name,
                standing=standing_label(rep),
                rep=rep,
                description=faction.description,
            )
        )
    return lines
