"""
Generated faction missions — the quests-vs-missions split.

Kill and collect contracts are machine-generated from faction config; they
are never hand-written. Hand-crafted puzzle quests are a separate future
system. One active mission at a time; it lives in the ``mission`` state block
so persistence is free.

Mission shape:
    {"faction": id, "kind": "kill"|"collect", "target": template_id,
     "count": int, "progress": int}
"""

import random
from typing import Any

from sage.api import log_event, t

from .models import FactionModel, standing_name
from .registry import FactionRegistry
from .standing import adjust_rep, get_rep

MISSION_KEY = "mission"
# Standings (by id) that refuse to hand out work.
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
    options += [("kill", tid, KILL_COUNT_RANGE) for tid in faction.enemies]
    options += [("collect", tid, COLLECT_COUNT_RANGE) for tid in faction.wanted_items]
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
    return t(
        "factions.mission.kill" if mission.get("kind") == "kill" else "factions.mission.collect",
        count=mission.get("count", 0),
        target=mission.get("target", "?"),
        faction=faction.name if faction else mission.get("faction", "?"),
        progress=mission.get("progress", 0),
    )


def record_kill(
    stats: dict[str, Any], registry: FactionRegistry, template_id: str, wallet: Any = None
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
        return [t("factions.mission.progress", mission=describe_mission(mission, registry))], False
    return _complete(stats, registry, mission, wallet), True


def try_complete_collect(
    stats: dict[str, Any],
    registry: FactionRegistry,
    inventory: list[dict[str, Any]],
    wallet: Any = None,
) -> tuple[list[str], list[dict[str, Any]] | None]:
    """
    Complete an active collect mission from an in-hand inventory list.
    Returns (messages, new_inventory) — new_inventory is None when nothing
    changed (no mission / wrong kind / not enough items).
    """
    mission = active_mission(stats)
    if not mission or mission.get("kind") != "collect":
        return [t("factions.mission.no_delivery")], None
    target = mission.get("target", "")
    needed = int(mission.get("count", 0))
    have = [it for it in inventory if it.get("template") == target]
    if len(have) < needed:
        return [
            t(
                "factions.mission.short",
                needed=needed,
                target=target,
                have=len(have),
                mission=describe_mission(mission, registry),
            )
        ], None
    consumed_ids = {it.get("id") for it in have[:needed]}
    new_inventory = [it for it in inventory if it.get("id") not in consumed_ids]
    messages = _complete(stats, registry, mission, wallet)
    return messages, new_inventory


def _complete(
    stats: dict[str, Any], registry: FactionRegistry, mission: dict[str, Any], wallet: Any
) -> list[str]:
    """Pay out a finished mission; money goes through the engine wallet when the world has one."""
    stats[MISSION_KEY] = None
    faction = registry.get(mission.get("faction", ""))
    log_event(
        "mission_complete",
        faction=mission.get("faction", ""),
        mission_kind=mission.get("kind", ""),
        target=mission.get("target", ""),
        count=mission.get("count", 0),
    )
    messages = [t("factions.mission.complete", mission=describe_mission(mission, registry))]
    if faction is not None:
        crossing = adjust_rep(stats, faction, faction.mission_rep)
        pay = int(getattr(faction, "mission_pay", 0) or 0)
        if pay > 0 and wallet is not None and wallet.enabled:
            wallet.credit(stats, pay)
            messages.append(
                t(
                    "factions.mission.paid",
                    faction=faction.name,
                    rep=faction.mission_rep,
                    pay=pay,
                    currency=wallet.name(),
                )
            )
        else:
            messages.append(
                t("factions.mission.rep_only", faction=faction.name, rep=faction.mission_rep)
            )
        if crossing:
            messages.append(crossing)
    return messages
