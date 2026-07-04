"""Deterministic proficiency advancement and resonance-cap decay."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from fablestar.proficiencies.models import ProficiencyState
from fablestar.proficiencies.registry import ProficiencyRegistry
from fablestar.proficiencies.state_helpers import (
    CONDUIT_KEY,
    decay_floor_for_peak,
    ensure_proficiency_block,
    total_proficiency_levels,
)


@dataclass
class GainResult:
    ok: bool
    message: str
    delta_levels: int = 0


class ProficiencyEngine:
    TOTAL_CAP = 5000
    LEAF_CAP = 200

    def __init__(self, registry: ProficiencyRegistry):
        self.registry = registry

    def _level(self, stats: dict[str, Any], pid: str) -> int:
        ensure_proficiency_block(stats)
        row = stats[CONDUIT_KEY]["proficiencies"].get(pid) or {}
        return int(row.get("level", 0))

    def _set_level(self, stats: dict[str, Any], pid: str, level: int, *, bump_peak: bool) -> None:
        ensure_proficiency_block(stats)
        prof = stats[CONDUIT_KEY]["proficiencies"]
        row = dict(prof.get(pid) or {"level": 0, "state": "raise", "peak": 0})
        level = max(0, min(self.LEAF_CAP, int(level)))
        row["level"] = level
        if bump_peak:
            row["peak"] = max(int(row.get("peak", 0)), level)
        prof[pid] = row

    def _state(self, stats: dict[str, Any], pid: str) -> ProficiencyState:
        ensure_proficiency_block(stats)
        row = stats[CONDUIT_KEY]["proficiencies"].get(pid) or {}
        s = row.get("state", "raise")
        if s in ("raise", "lower", "lock"):
            return s  # type: ignore[return-value]
        return "raise"

    def _gate_ok(self, stats: dict[str, Any], leaf_id: str) -> bool:
        """
        Branch investment gate (Fablestar Expanse spec): immediate parent must be at tier * 5,
        where tier is the dot-segment count of this leaf (e.g. combat.melee.blades -> 3 -> parent >= 15).
        """
        node = self.registry.get_node(leaf_id)
        if not node or not node.is_leaf:
            return False
        parent_id = node.parent_id
        if not parent_id:
            return True
        tier = len(leaf_id.split("."))
        need = tier * 5
        return self._level(stats, parent_id) >= need

    def _ensure_internal_chain(self, stats: dict[str, Any], leaf_id: str) -> None:
        """Ensure dict rows exist for all prefix ids so parents can hold levels."""
        node = self.registry.get_node(leaf_id)
        if not node:
            return
        parts = leaf_id.split(".")
        for i in range(1, len(parts)):
            pid = ".".join(parts[:i])
            if pid not in self.registry.nodes:
                continue
            ensure_proficiency_block(stats)
            prof = stats[CONDUIT_KEY]["proficiencies"]
            if pid not in prof:
                prof[pid] = {"level": 0, "state": "raise", "peak": 0}

    def apply_decay(self, stats: dict[str, Any], amount: int) -> int:
        """Public: decay `amount` total levels from leaves in `lower` state (respect floor). Returns applied."""
        if amount <= 0:
            return 0
        ensure_proficiency_block(stats)
        prof = stats[CONDUIT_KEY]["proficiencies"]
        candidates: list[tuple[str, int, int]] = []  # (pid, lvl, floor_v)
        for pid, row in prof.items():
            if row.get("state") != "lower":
                continue
            if not self.registry.get_node(pid):
                continue
            peak = int(row.get("peak", row.get("level", 0)))
            lvl = int(row.get("level", 0))
            floor_v = decay_floor_for_peak(peak)
            if lvl > floor_v:
                candidates.append((pid, lvl, floor_v))
        candidates.sort(key=lambda t: t[1], reverse=True)
        applied = 0
        for pid, lvl, floor_v in candidates:
            if applied >= amount:
                break
            headroom = lvl - floor_v
            if headroom <= 0:
                continue
            dec = min(headroom, amount - applied)
            row = prof[pid]
            row["level"] = lvl - dec
            prof[pid] = row
            applied += dec
        return applied

    def _enforce_total_cap(self, stats: dict[str, Any]) -> None:
        over = total_proficiency_levels(stats, None, registry=self.registry) - self.TOTAL_CAP
        if over > 0:
            self.apply_decay(stats, over)

    def try_field_gain(
        self,
        stats: dict[str, Any],
        leaf_id: str,
        *,
        vr: bool = False,
        field_success: bool | None = None,
        roll_value: float | None = None,
    ) -> GainResult:
        """Attempt +1 level on a leaf via field acquisition.

        vr: True if acquired in a virtual-reality context (reduced gain chance).
        field_success: if set, override the random roll (True = always gain, False = never gain).
        roll_value: 0..1 uniform substitute for the random roll (deterministic tests).
        """
        ensure_proficiency_block(stats)
        leaf = self.registry.get_leaf(leaf_id)
        if not leaf:
            return GainResult(False, "unknown_leaf")
        if self._state(stats, leaf_id) != "raise":
            return GainResult(False, "leaf_not_raise_state")
        self._ensure_internal_chain(stats, leaf_id)
        if not self._gate_ok(stats, leaf_id):
            return GainResult(False, "depth_gate")

        if field_success is True:
            success = True
        elif field_success is False:
            success = False
        else:
            lo, hi = 0.35, 0.65
            p = lo + random.random() * (hi - lo)
            if vr:
                p *= 0.75
            rv = random.random() if roll_value is None else float(roll_value)
            success = rv < p

        if not success:
            return GainResult(False, "field_roll_failed")

        cur = self._level(stats, leaf_id)
        if cur >= self.LEAF_CAP:
            return GainResult(False, "leaf_cap")

        if total_proficiency_levels(stats, None, registry=self.registry) >= self.TOTAL_CAP:
            return GainResult(False, "resonance_cap")

        self._set_level(stats, leaf_id, cur + 1, bump_peak=True)
        self._enforce_total_cap(stats)
        return GainResult(True, "gained", delta_levels=1)

    def try_mentored_gain(
        self,
        stats: dict[str, Any],
        leaf_id: str,
        *,
        teacher_leaf_level: int,
    ) -> GainResult:
        """+1 if teacher is 50%+ higher on same leaf level."""
        student = self._level(stats, leaf_id)
        if teacher_leaf_level < int((1.5 * student) + 0.999):
            return GainResult(False, "teacher_not_advanced_enough")
        return self.try_field_gain(stats, leaf_id, field_success=True)

    def try_archive_study(
        self,
        stats: dict[str, Any],
        leaf_id: str,
        *,
        domain_cap_remaining: int,
    ) -> GainResult:
        """Guaranteed +1 if domain cap allows (caller enforces RP spend)."""
        if domain_cap_remaining <= 0:
            return GainResult(False, "archive_domain_cap")
        r = self.try_field_gain(stats, leaf_id, field_success=True)
        if r.ok:
            dom = leaf_id.split(".", 1)[0]
            ensure_proficiency_block(stats)
            spent = stats[CONDUIT_KEY]["archive_domain_spent"]
            spent[dom] = int(spent.get(dom, 0)) + 1
        return r
