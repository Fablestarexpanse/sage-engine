"""Player-facing proficiency / Conduit readouts (deterministic; no LLM)."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from sage.api import PluginAPI

from .bonus import calculate_proficiency_bonus
from .registry import ProficiencyRegistry
from .state_helpers import CONDUIT_KEY, ensure_proficiency_block, total_proficiency_levels


def _top_leaves(
    stats: dict, registry: ProficiencyRegistry, limit: int = 8
) -> list[tuple[str, int]]:
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    scored: list[tuple[str, int]] = []
    for lid in registry.leaf_ids:
        lv = int((prof.get(lid) or {}).get("level", 0))
        if lv > 0:
            scored.append((lid, lv))
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


def _parse_proficiency_id(args: list[str]) -> str:
    return ".".join(a.strip() for a in args if a.strip())


def register(api: PluginAPI, registry: Callable[[], ProficiencyRegistry]) -> None:
    async def stats_of(session: Any) -> dict[str, Any]:
        stats = await api.state.snapshot(session.player_id)
        ensure_proficiency_block(stats)
        return stats

    async def score_cmd(session, args):
        """Show conduit attributes, resonance total, and top proficiencies."""
        stats = await stats_of(session)
        ca = stats[CONDUIT_KEY]["conduit_attributes"]
        reg = registry()
        total = total_proficiency_levels(stats, registry=reg)
        lines = [
            "— Conduit —",
            f"FRT {ca.get('FRT', 10)}  RFX {ca.get('RFX', 10)}  ACU {ca.get('ACU', 10)}  RSV {ca.get('RSV', 10)}  PRS {ca.get('PRS', 10)}",
            f"Resonance (proficiency levels): {total} / {reg.total_level_cap()}",
        ]
        top = _top_leaves(stats, reg)
        if top:
            lines.append("Top proficiencies:")
            for lid, lv in top:
                short = lid.split(".")[-1].replace("_", " ")
                lines.append(f"  {short}: {lv}  ({lid})")
        else:
            lines.append("No proficiency levels yet — use skills in context (e.g. combat) to gain.")
        await session.send("\r\n".join(lines))

    async def prof_cmd(session, args):
        """List all non-zero proficiencies (compact)."""
        stats = await stats_of(session)
        prof = stats[CONDUIT_KEY]["proficiencies"]
        reg = registry()
        rows: list[str] = []
        for lid in sorted(reg.leaf_ids):
            row = prof.get(lid) or {}
            lv = int(row.get("level", 0))
            if lv <= 0:
                continue
            node = reg.get_node(lid)
            rows.append(f"{node.name if node else lid} ({lid}): {lv} [{row.get('state', 'raise')}]")
        if not rows:
            await session.send("You have no proficiency levels recorded yet.")
            return
        total = total_proficiency_levels(stats, registry=reg)
        body = [
            f"Proficiencies ({len(rows)} leaves, {total} / {reg.total_level_cap()} total levels):",
            *rows[:60],
        ]
        if len(rows) > 60:
            body.append("… (trimmed; use score for highlights)")
        await session.send("\r\n".join(body))

    async def cap_cmd(session, args):
        """Resonance capacity: total levels vs hard cap, counts by raise/lower/lock."""
        stats = await stats_of(session)
        prof = stats[CONDUIT_KEY]["proficiencies"]
        reg = registry()
        total = total_proficiency_levels(stats, registry=reg)
        cap = reg.total_level_cap()
        util = (100.0 * total / cap) if cap else 0.0
        states = [(prof.get(lid) or {}).get("state", "raise") for lid in reg.leaf_ids]
        lines = [
            f"Resonance capacity: {total:,} / {cap:,} ({util:.1f}%)",
            f"Remaining headroom: {max(0, cap - total):,} levels (catalog leaves only).",
            f"Leaves — raise: {sum(s not in ('lower', 'lock') for s in states)}  "
            f"lower: {states.count('lower')}  lock: {states.count('lock')}",
        ]
        await session.send("\r\n".join(lines))

    async def bonus_cmd(session, args):
        """Show bonus breakdown for one leaf proficiency: bonus <id> (e.g. combat.melee.blades)."""
        leaf_id = _parse_proficiency_id(args)
        if not leaf_id:
            await session.send(
                "Usage: bonus <proficiency.id>  — example: bonus combat.melee.blades"
            )
            return
        reg = registry()
        leaf = reg.get_leaf(leaf_id)
        node = reg.get_node(leaf_id)
        if not leaf or not node or not node.is_leaf:
            await session.send(f"Unknown leaf proficiency: {leaf_id}")
            return
        stats = await stats_of(session)
        prof = stats[CONDUIT_KEY]["proficiencies"]
        ca = stats[CONDUIT_KEY]["conduit_attributes"]
        row = prof.get(leaf_id) or {}
        lv = int(row.get("level", 0))
        w = dict(leaf.stat_weights or {})
        wstr = ", ".join(f"{k} {v:g}" for k, v in sorted(w.items()) if float(v) > 0) or "(none)"
        frt, rfx, acu, rsv, prs = (int(ca.get(k, 10)) for k in ("FRT", "RFX", "ACU", "RSV", "PRS"))
        stat_product = 1.0
        for stat_name, weight in w.items():
            if float(weight) > 0:
                stat_product *= max(1.0, float(ca.get(str(stat_name).upper(), 10))) ** float(weight)
        lines = [
            f"{node.name} ({leaf_id})",
            f"Level: {lv}  Peak: {int(row.get('peak', lv))}  State: {row.get('state', 'raise')}",
            f"Stat weights: {wstr}",
            f"Your conduit: FRT {frt}  RFX {rfx}  ACU {acu}  RSV {rsv}  PRS {prs}",
            f"Stat factor (weighted product): {stat_product:.3f}"
            if lv > 0
            else "Stat factor: n/a (level 0)",
            f"Level factor (√level): {math.sqrt(lv):.3f}" if lv > 0 else "Level factor: 0",
            f"Computed bonus: {calculate_proficiency_bonus(lv, ca, w)}",
        ]
        await session.send("\r\n".join(lines))

    def set_state(new_state: str):
        async def handler(session, args):
            leaf_id = _parse_proficiency_id(args)
            if not leaf_id:
                await session.send(f"Usage: {new_state} <proficiency.id>")
                return
            node = registry().get_node(leaf_id)
            if not node or not node.is_leaf:
                await session.send(f"Unknown leaf proficiency: {leaf_id}")
                return
            async with api.state.edit(session.player_id) as stats:
                ensure_proficiency_block(stats)
                prof = stats[CONDUIT_KEY]["proficiencies"]
                row = dict(prof.get(leaf_id) or {"level": 0, "state": "raise", "peak": 0})
                row["state"] = new_state
                prof[leaf_id] = row
            await session.send(f"{leaf_id}: advancement state set to [{new_state}].")

        handler.__doc__ = {
            "raise": "Mark a leaf as raise (allow field gains). Usage: raise <proficiency.id>",
            "lower": "Mark a leaf as lower (decays when over resonance cap). Usage: lower <proficiency.id>",
            "lock": "Mark a leaf as lock (no field gains). Usage: lock <proficiency.id>",
        }[new_state]
        return handler

    api.commands.register("score", score_cmd, aliases=["sheet", "conduit", "stats"])
    api.commands.register("prof", prof_cmd, aliases=["proficiencies", "skills"])
    api.commands.register("cap", cap_cmd, aliases=["capacity", "resonance"])
    api.commands.register("bonus", bonus_cmd)
    api.commands.register("raise", set_state("raise"), aliases=["raise_prof"])
    api.commands.register("lower", set_state("lower"), aliases=["lower_prof"])
    api.commands.register("lock", set_state("lock"), aliases=["lock_prof"])
