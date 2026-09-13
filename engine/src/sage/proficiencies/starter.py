"""Chargen: distribute a fixed budget of proficiency levels across catalog leaves."""

from __future__ import annotations

from typing import Any

from sage.proficiencies.models import ProficiencyLeafDefinition
from sage.proficiencies.registry import ProficiencyRegistry
from sage.proficiencies.state_helpers import CONDUIT_KEY, ensure_proficiency_block

STARTER_POINTS_BUDGET = 15
STARTER_MAX_PER_LEAF = 5


def coerce_starter_level(raw: Any) -> int | None:
    """A whole-number level from JSON, or None when the value isn't one.

    Accepts ints and integral floats (2.0). Rejects bools, strings, fractions,
    NaN and infinities instead of truncating them: int(5.9) would quietly
    become 5 and int(inf) raises OverflowError.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    return None


def validate_starter_allocation(
    allocation: dict[str, int],
    registry: ProficiencyRegistry,
) -> tuple[bool, str]:
    """Return (ok, error_message). Empty allocation is valid (use server defaults only)."""
    if not allocation:
        return True, ""
    total = 0
    for lid, raw in allocation.items():
        if not isinstance(lid, str) or not lid.strip():
            return False, "invalid_proficiency_id"
        lid = lid.strip()
        if registry.get_leaf(lid) is None:
            return False, f"unknown_proficiency:{lid}"
        n = coerce_starter_level(raw)
        if n is None:
            return False, f"invalid_level:{lid}"
        if n < 0 or n > STARTER_MAX_PER_LEAF:
            return False, f"level_out_of_range:{lid}"
        total += n
    if total > STARTER_POINTS_BUDGET:
        return False, "starter_budget_exceeded"
    return True, ""


def _ensure_parent_branch_levels_for_gates(
    stats: dict[str, Any], allocation: dict[str, int], registry: ProficiencyRegistry
) -> None:
    """
    Depth gate (tier * 5 on immediate parent) must be satisfied for field gains.
    Prefix rows are not catalog leaves, so they do not count toward the 5,000 resonance cap
    but must exist at sufficient level when a starter leaf is boosted.
    """
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    for lid, n in allocation.items():
        if int(n) <= 0:
            continue
        if registry.get_leaf(lid) is None:
            continue
        parts = lid.split(".")
        for i in range(1, len(parts)):
            child_id = ".".join(parts[: i + 1])
            parent_id = ".".join(parts[:i])
            if not parent_id or child_id not in registry.nodes:
                continue
            tier = len(child_id.split("."))
            need = tier * 5
            row = dict(prof.get(parent_id) or {"level": 0, "state": "raise", "peak": 0})
            cur = int(row.get("level", 0))
            if cur < need:
                row["level"] = need
                row["peak"] = max(int(row.get("peak", 0)), need)
                prof[parent_id] = row


def apply_starter_to_stats(
    stats: dict[str, Any], allocation: dict[str, int], registry: ProficiencyRegistry
) -> None:
    """Merge allocation into stats[conduit][proficiencies] (mutates stats)."""
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    for lid, n in allocation.items():
        if n <= 0:
            continue
        if registry.get_leaf(lid) is None:
            continue
        prof[lid] = {"level": int(n), "state": "raise", "peak": int(n)}
    if allocation:
        _ensure_parent_branch_levels_for_gates(stats, allocation, registry)


def _leaf_detail_blurb(leaf: ProficiencyLeafDefinition, leaf_id: str) -> str:
    """Human-readable explanation when catalog description is empty."""
    path_readable = " > ".join(p.replace("_", " ") for p in leaf_id.split(".") if p)
    parts: list[str] = [f"Skill path: {path_readable}."]
    if leaf.tags:
        parts.append("Tags: " + ", ".join(leaf.tags[:12]))
    if leaf.stat_weights:
        ranked = sorted(leaf.stat_weights.items(), key=lambda kv: (-kv[1], kv[0]))
        mix = ", ".join(f"{k} {v * 100:.0f}%" for k, v in ranked)
        parts.append(f"Conduit weight mix (FRT / RFX / ACU / RSV / PRS): {mix}.")
    parts.append(
        "Levels represent trained aptitude; the MUD uses this (and related skills) for checks and progression."
    )
    return " ".join(parts)


def catalog_leaves_for_client(registry: ProficiencyRegistry) -> list[dict[str, Any]]:
    """Leaf list for chargen picker (includes detail text for UI tooltips)."""
    out: list[dict[str, Any]] = []
    for lid in sorted(registry.leaf_ids):
        leaf = registry.get_leaf(lid)
        node = registry.get_node(lid)
        if not leaf or not node:
            continue
        desc = (leaf.description or "").strip()
        detail = desc if desc else _leaf_detail_blurb(leaf, lid)
        w = dict(leaf.stat_weights or {})
        out.append(
            {
                "id": lid,
                "domain": leaf.domain,
                "name": node.name or lid.split(".")[-1].replace("_", " ").title(),
                "detail": detail,
                "stat_weights": w,
            }
        )
    return out
