"""Character.stats JSON helpers for Conduit proficiency block."""

from __future__ import annotations

import math
from collections.abc import MutableMapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .registry import ProficiencyRegistry

from .models import ConduitAttributes, ProficiencyStatsBlock

CONDUIT_KEY = "conduit"
ATTRIBUTES_KEY = "conduit_attributes"


def _default_conduit_dict() -> dict[str, Any]:
    return ProficiencyStatsBlock().model_dump()


def ensure_proficiency_block(stats: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Mutate and return stats with a nested conduit proficiency block."""
    if CONDUIT_KEY not in stats or not isinstance(stats[CONDUIT_KEY], dict):
        stats[CONDUIT_KEY] = _default_conduit_dict()
    block = stats[CONDUIT_KEY]
    block.setdefault("version", 1)
    block.setdefault(ATTRIBUTES_KEY, ConduitAttributes().model_dump())
    block.setdefault("proficiencies", {})
    block.setdefault("archive_domain_spent", {})
    block.setdefault("combat_hybrid_legacy", True)
    return stats


def proficiency_block(stats: MutableMapping[str, Any]) -> dict[str, Any]:
    """The character's proficiency block, created with defaults when missing."""
    return ensure_proficiency_block(stats)[CONDUIT_KEY]


def migrate_legacy_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Map legacy D&D-like keys into conduit_attributes; preserves original keys."""
    out = deepcopy(stats)
    if any(k in out for k in ("strength", "dexterity", "intelligence", "perception")):
        ensure_proficiency_block(out)
        ca = proficiency_block(out)[ATTRIBUTES_KEY]
        s = int(out.get("strength", 10))
        d = int(out.get("dexterity", 10))
        i = int(out.get("intelligence", 10))
        p = int(out.get("perception", 10))
        ca["FRT"] = max(1, min(200, 10 + max(0, s - 10) // 2))
        ca["RFX"] = max(1, min(200, 10 + max(0, d - 10) // 2))
        ca["ACU"] = max(1, min(200, 10 + max(0, i - 10) // 2 + max(0, p - 10) // 4))
        ca["RSV"] = max(1, min(200, 10 + max(0, i - 10) // 4))
        ca["PRS"] = max(1, min(200, 10 + max(0, p - 10) // 2))
    ensure_proficiency_block(out)
    return out


def total_proficiency_levels(
    stats: dict[str, Any],
    leaf_ids: list[str] | None = None,
    *,
    registry: ProficiencyRegistry | None = None,
) -> int:
    """Sum levels for catalog leaves only (internal prefix nodes excluded unless listed)."""
    prof = proficiency_block(stats)["proficiencies"]
    if leaf_ids is None:
        if registry is not None:
            leaf_ids = list(registry.leaf_ids)
        else:
            leaf_ids = list(prof.keys())
    t = 0
    for lid in leaf_ids:
        row = prof.get(lid) or {}
        t += int(row.get("level", 0))
    return t


def combat_attack_defense_from_stats(
    stats: dict[str, Any],
    *,
    hybrid_legacy: bool = True,
) -> tuple[int, int]:
    """
    Derive simple attack/defense integers for combat.py.
    Hybrid: uses legacy strength/dexterity when present and hybrid flag True.
    """
    ensure_proficiency_block(stats)
    ca = stats[CONDUIT_KEY]["conduit_attributes"]
    frt = int(ca.get("FRT", 10))
    rfx = int(ca.get("RFX", 10))
    acu = int(ca.get("ACU", 10))

    melee_ids = [
        "combat.melee.blades",
        "combat.melee.impact",
        "combat.melee.polearms",
        "combat.melee.unarmed",
    ]
    prof = stats[CONDUIT_KEY]["proficiencies"]
    melee_sum = sum(int((prof.get(lid) or {}).get("level", 0)) for lid in melee_ids)

    prof_attack = max(1, (frt + rfx + acu) // 18 + melee_sum // 40)
    prof_def = max(1, (rfx + acu) // 15 + melee_sum // 50)

    hybrid_flag = bool(stats[CONDUIT_KEY].get("combat_hybrid_legacy", True))
    if hybrid_legacy and hybrid_flag:
        leg_a = int(stats.get("strength", 10)) // 3
        leg_d = int(stats.get("dexterity", 10)) // 5
        return max(prof_attack, leg_a), max(prof_def, leg_d)
    return prof_attack, prof_def


def decay_floor_for_peak(peak: int) -> int:
    return math.floor(0.75 * float(peak))


# Progression slot providers (sage.world.progression) while proficiencies are engine code.


def seed_attributes(stats: dict[str, Any], attributes: dict[str, int]) -> None:
    """progression.seed_attributes: a new character's attribute spread (unknown keys ignored)."""
    attrs = proficiency_block(stats)[ATTRIBUTES_KEY]
    for key, value in attributes.items():
        if key in attrs:
            attrs[key] = int(value)


def total_levels(stats: dict[str, Any]) -> int:
    """progression.total_levels: every proficiency level summed."""
    try:
        return int(total_proficiency_levels(stats))
    except Exception:
        return 0


def skill_sheet(stats: dict[str, Any]) -> dict[str, Any]:
    """progression.skill_sheet: attribute spread plus leaf levels, highest first."""
    block = proficiency_block(deepcopy(stats))
    profs = block["proficiencies"]
    leaves = sorted(
        (
            {
                "id": pid,
                "level": int(p.get("level", 0)),
                "peak": int(p.get("peak", 0)),
                "state": p.get("state", ""),
            }
            for pid, p in profs.items()
            if isinstance(p, dict)
        ),
        key=lambda r: (-r["level"], -r["peak"], r["id"]),
    )
    return {"attributes": block[ATTRIBUTES_KEY], "leaves": leaves}
