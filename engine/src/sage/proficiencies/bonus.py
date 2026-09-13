"""Deterministic proficiency bonus from level + Conduit attributes (spec: Discworld-style curve)."""

from __future__ import annotations

import math
from collections.abc import Mapping, MutableMapping
from typing import Any

# Character creation target (Fablestar Expanse spec); validation for future chargen UIs / admin tools.
CONDUIT_CHARGEN_POINTS_TOTAL = 65
CONDUIT_STAT_MIN = 8
CONDUIT_STAT_MAX = 23


def calculate_proficiency_bonus(
    level: int,
    conduit_attributes: Mapping[str, Any],
    stat_weights: Mapping[str, float],
) -> int:
    """
    Effective bonus for checks: sqrt(level) * weighted geometric mean of stats / 10.

    level 0 -> 0. Weights should sum to ~1.0 on the leaf definition.
    """
    lv = int(level)
    if lv <= 0:
        return 0

    level_factor = math.sqrt(float(lv))
    stat_product = 1.0
    for stat_name, weight in (stat_weights or {}).items():
        w = float(weight)
        if w <= 0:
            continue
        key = str(stat_name).upper()
        raw = conduit_attributes.get(key, conduit_attributes.get(stat_name, 10))
        val = max(1.0, float(raw))
        stat_product *= val**w

    bonus = level_factor * stat_product / 10.0
    return int(bonus)


def validate_chargen_conduit_allocation(attrs: Mapping[str, Any]) -> tuple[bool, str]:
    """
    True if five stats each in [CONDUIT_STAT_MIN, CONDUIT_STAT_MAX] and sum to CONDUIT_CHARGEN_POINTS_TOTAL.
    Keys FRT, RFX, ACU, RSV, PRS (case-insensitive).
    """
    keys = ("FRT", "RFX", "ACU", "RSV", "PRS")
    vals: list[int] = []
    for k in keys:
        v = attrs.get(k, attrs.get(k.lower()))
        if v is None:
            return False, f"missing_{k.lower()}"
        try:
            n = int(v)
        except (TypeError, ValueError):
            return False, f"invalid_{k.lower()}"
        if n < CONDUIT_STAT_MIN or n > CONDUIT_STAT_MAX:
            return False, f"{k.lower()}_out_of_range"
        vals.append(n)
    if sum(vals) != CONDUIT_CHARGEN_POINTS_TOTAL:
        return False, "conduit_total_not_65"
    return True, ""


def apply_chargen_defaults(stats: MutableMapping[str, Any]) -> None:
    """Set conduit_attributes to spec default (13 each) when block is missing keys."""
    from sage.proficiencies.state_helpers import CONDUIT_KEY, ensure_proficiency_block

    ensure_proficiency_block(stats)
    ca = stats[CONDUIT_KEY]["conduit_attributes"]
    for k in ("FRT", "RFX", "ACU", "RSV", "PRS"):
        if k not in ca or ca[k] is None:
            ca[k] = 13
            continue
        try:
            int(ca[k])
        except (TypeError, ValueError):
            ca[k] = 13
