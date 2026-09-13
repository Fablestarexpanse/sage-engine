"""
Generated faction missions — Epitaph's quests-vs-missions split (roadmap C6).

Kill and collect contracts are machine-generated from faction config; they
are never hand-written. Hand-crafted puzzle quests are a separate future
system. One active mission at a time; it lives in the stats blob under
"mission" so persistence is free.

Mission shape:
    {"faction": id, "kind": "kill"|"collect", "target": template_id,
     "count": int, "progress": int}
"""

import random
from typing import Any

from fablestar.factions.engine import adjust_rep, get_rep
from fablestar.factions.models import FactionModel, standing_name
from fablestar.factions.registry import FactionRegistry

MISSION_KEY = "mission"
# Standings (by name) that refuse to hand out work.
UNFRIENDLY = {"loathed", "hated"}
KILL_COUNT_RANGE = (3, 5)
COLLECT_COUNT_RANGE = (2, 3)


def active_mission(stats: dict[str, Any]) -> dict[str, Any] | None:
    m = stats.get(MISSION_KEY)
    return m if isinstance(m, dict) and m.get("kind") else None


def will_deal(stats: dict[str, Any], faction: FactionModel) -> bool:
    return standing_name(get_rep(stats, faction)) not in UNFRIENDLY


def generate_mission(
    faction: FactionModel, rng: random.Random | None = None
) -> dict[str, Any] | None:
    """Roll one contract from the faction's config; None when it offers none."""
    rng = rng or random.Random()
    options: list[tuple[str, str, tuple[int, int]]] = []
    options += [("kill", t, KILL_COUNT_RANGE) for t in faction.enemies]
    options += [("collect", t, COLLECT_COUNT_RANGE) for t in faction.wanted_items]
    if not options:
        return None
    kind, target, (lo, hi) = rng.choice(options)
    return {
        "faction": faction.id,
        "kind": kind,
        "target": target,
        "count": rng.randint(lo, hi),
        "progress": 0,
    }


def describe_mission(mission: dict[str, Any], registry: FactionRegistry) -> str:
    faction = registry.get(mission.get("faction", ""))
    fname = faction.name if faction else mission.get("faction", "?")
    verb = "Destroy" if mission.get("kind") == "kill" else "Deliver"
    return (
        f"{verb} {mission.get('count', 0)}x {mission.get('target', '?')} for {fname} "
        f"({mission.get('progress', 0)}/{mission.get('count', 0)})"
    )


def record_kill(
    stats: dict[str, Any], registry: FactionRegistry, template_id: str
) -> tuple[list[str], bool]:
    """
    Advance an active kill mission after a kill. Returns (messages, completed).
    Completion pays rep immediately — no turn-in NPC exists yet.
    """
    mission = active_mission(stats)
    if not mission or mission.get("kind") != "kill" or mission.get("target") != template_id:
        return [], False
    mission["progress"] = int(mission.get("progress", 0)) + 1
    if mission["progress"] < int(mission.get("count", 0)):
        return [f"Mission: {describe_mission(mission, registry)}"], False
    return _complete(stats, registry, mission), True


def try_complete_collect(
    stats: dict[str, Any],
    registry: FactionRegistry,
    inventory: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]] | None]:
    """
    Complete an active collect mission from an in-hand inventory list.
    Returns (messages, new_inventory) — new_inventory is None when nothing
    changed (no mission / wrong kind / not enough items).
    """
    mission = active_mission(stats)
    if not mission or mission.get("kind") != "collect":
        return ["You have no delivery to complete."], None
    target = mission.get("target", "")
    needed = int(mission.get("count", 0))
    have = [it for it in inventory if it.get("template") == target]
    if len(have) < needed:
        return [
            f"You need {needed}x {target} but are carrying {len(have)}. "
            f"Mission: {describe_mission(mission, registry)}"
        ], None
    consumed_ids = {it.get("id") for it in have[:needed]}
    new_inventory = [it for it in inventory if it.get("id") not in consumed_ids]
    messages = _complete(stats, registry, mission)
    return messages, new_inventory


def _complete(
    stats: dict[str, Any], registry: FactionRegistry, mission: dict[str, Any]
) -> list[str]:
    stats[MISSION_KEY] = None
    faction = registry.get(mission.get("faction", ""))
    messages = [f"Mission complete: {describe_mission(mission, registry)}"]
    if faction is not None:
        crossing = adjust_rep(stats, faction, faction.mission_rep)
        pay = int(getattr(faction, "mission_pay", 0) or 0)
        if pay > 0:
            stats["digi"] = int(stats.get("digi", 0) or 0) + pay
            messages.append(
                f"{faction.name} credits your account ({faction.mission_rep:+d} rep, +{pay} Digi)."
            )
        else:
            messages.append(f"{faction.name} credits your account ({faction.mission_rep:+d} rep).")
        if crossing:
            messages.append(crossing)
    return messages
