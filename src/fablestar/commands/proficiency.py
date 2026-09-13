"""Player-facing proficiency / conduit readouts (deterministic; no LLM)."""

from __future__ import annotations

import math

from fablestar.commands.registry import command
from fablestar.network.session import Session
from fablestar.proficiencies.bonus import calculate_proficiency_bonus
from fablestar.proficiencies.state_helpers import (
    CONDUIT_KEY,
    ensure_proficiency_block,
    total_proficiency_levels,
)


def _top_leaves(stats: dict, registry, limit: int = 8) -> list[tuple[str, int]]:
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    scored: list[tuple[str, int]] = []
    for lid in registry.leaf_ids:
        row = prof.get(lid) or {}
        lv = int(row.get("level", 0))
        if lv > 0:
            scored.append((lid, lv))
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


def _parse_proficiency_id(args: list[str]) -> str:
    return ".".join(a.strip() for a in args if a.strip())


@command("score", aliases=["sheet", "conduit", "stats"])
async def score_cmd(session: Session, args: list[str]):
    """Show conduit attributes, resonance total, and top proficiencies."""
    from fablestar.app import app_instance

    del args
    player_id = session.player_id
    if not player_id:
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    ensure_proficiency_block(stats)
    ca = stats[CONDUIT_KEY]["conduit_attributes"]
    reg = app_instance.content_loader.get_proficiency_registry()
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


@command("prof", aliases=["proficiencies", "skills"])
async def prof_cmd(session: Session, args: list[str]):
    """List all non-zero proficiencies (compact)."""
    from fablestar.app import app_instance

    del args
    player_id = session.player_id
    if not player_id:
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    reg = app_instance.content_loader.get_proficiency_registry()
    rows: list[str] = []
    for lid in sorted(reg.leaf_ids):
        row = prof.get(lid) or {}
        lv = int(row.get("level", 0))
        if lv <= 0:
            continue
        node = reg.get_node(lid)
        label = node.name if node else lid
        st = row.get("state", "raise")
        rows.append(f"{label} ({lid}): {lv} [{st}]")
    if not rows:
        await session.send("You have no proficiency levels recorded yet.")
        return
    total = total_proficiency_levels(stats, registry=reg)
    header = f"Proficiencies ({len(rows)} leaves, {total} / {reg.total_level_cap()} total levels):"
    body = [header, *rows[:60]]
    if len(rows) > 60:
        body.append("… (trimmed; use score for highlights)")
    await session.send("\r\n".join(body))


@command("cap", aliases=["capacity", "resonance"])
async def cap_cmd(session: Session, args: list[str]):
    """Resonance capacity: total levels vs hard cap, counts by raise/lower/lock."""
    from fablestar.app import app_instance

    del args
    player_id = session.player_id
    if not player_id:
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    reg = app_instance.content_loader.get_proficiency_registry()
    total = total_proficiency_levels(stats, registry=reg)
    cap = reg.total_level_cap()
    remaining = max(0, cap - total)
    util = (100.0 * total / cap) if cap else 0.0
    n_raise = n_lower = n_lock = 0
    for lid in reg.leaf_ids:
        row = prof.get(lid) or {}
        st = row.get("state", "raise")
        if st == "lower":
            n_lower += 1
        elif st == "lock":
            n_lock += 1
        else:
            n_raise += 1
    lines = [
        f"Resonance capacity: {total:,} / {cap:,} ({util:.1f}%)",
        f"Remaining headroom: {remaining:,} levels (catalog leaves only).",
        f"Leaves — raise: {n_raise}  lower: {n_lower}  lock: {n_lock}",
    ]
    await session.send("\r\n".join(lines))


@command("bonus")
async def bonus_cmd(session: Session, args: list[str]):
    """Show bonus breakdown for one leaf proficiency: bonus <id> (e.g. combat.melee.blades)."""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    leaf_id = _parse_proficiency_id(args)
    if not leaf_id:
        await session.send("Usage: bonus <proficiency.id>  — example: bonus combat.melee.blades")
        return
    reg = app_instance.content_loader.get_proficiency_registry()
    leaf = reg.get_leaf(leaf_id)
    node = reg.get_node(leaf_id)
    if not leaf or not node or not node.is_leaf:
        await session.send(f"Unknown leaf proficiency: {leaf_id}")
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    ca = stats[CONDUIT_KEY]["conduit_attributes"]
    row = prof.get(leaf_id) or {}
    lv = int(row.get("level", 0))
    peak = int(row.get("peak", lv))
    st = row.get("state", "raise")
    w = dict(leaf.stat_weights or {})
    wstr = ", ".join(f"{k} {v:g}" for k, v in sorted(w.items()) if float(v) > 0) or "(none)"
    frt, rfx, acu, rsv, prs = (int(ca.get(k, 10)) for k in ("FRT", "RFX", "ACU", "RSV", "PRS"))
    b = calculate_proficiency_bonus(lv, ca, w)
    lf = math.sqrt(lv) if lv > 0 else 0.0
    stat_product = 1.0
    for stat_name, weight in w.items():
        wt = float(weight)
        if wt <= 0:
            continue
        key = str(stat_name).upper()
        val = max(1.0, float(ca.get(key, 10)))
        stat_product *= val**wt
    lines = [
        f"{node.name} ({leaf_id})",
        f"Level: {lv}  Peak: {peak}  State: {st}",
        f"Stat weights: {wstr}",
        f"Your conduit: FRT {frt}  RFX {rfx}  ACU {acu}  RSV {rsv}  PRS {prs}",
        f"Stat factor (weighted product): {stat_product:.3f}"
        if lv > 0
        else "Stat factor: n/a (level 0)",
        f"Level factor (√level): {lf:.3f}" if lv > 0 else "Level factor: 0",
        f"Computed bonus: {b}",
    ]
    await session.send("\r\n".join(lines))


async def _set_leaf_state(session: Session, args: list[str], new_state: str) -> None:
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    leaf_id = _parse_proficiency_id(args)
    if not leaf_id:
        await session.send(f"Usage: {new_state} <proficiency.id>")
        return
    reg = app_instance.content_loader.get_proficiency_registry()
    node = reg.get_node(leaf_id)
    if not node or not node.is_leaf:
        await session.send(f"Unknown leaf proficiency: {leaf_id}")
        return
    stats = await app_instance.redis.get_player_stats(player_id)
    ensure_proficiency_block(stats)
    prof = stats[CONDUIT_KEY]["proficiencies"]
    row = dict(prof.get(leaf_id) or {"level": 0, "state": "raise", "peak": 0})
    row["state"] = new_state
    prof[leaf_id] = row
    await app_instance.redis.set_player_stats(player_id, stats)
    await session.send(f"{leaf_id}: advancement state set to [{new_state}].")


@command("raise", aliases=["raise_prof"])
async def raise_prof_cmd(session: Session, args: list[str]):
    """Mark a leaf as raise (allow field gains). Usage: raise <proficiency.id>"""
    await _set_leaf_state(session, args, "raise")


@command("lower", aliases=["lower_prof"])
async def lower_prof_cmd(session: Session, args: list[str]):
    """Mark a leaf as lower (eligible for decay when over resonance cap). Usage: lower <proficiency.id>"""
    await _set_leaf_state(session, args, "lower")


@command("lock", aliases=["lock_prof"])
async def lock_prof_cmd(session: Session, args: list[str]):
    """Mark a leaf as lock (no field gains). Usage: lock <proficiency.id>"""
    await _set_leaf_state(session, args, "lock")
