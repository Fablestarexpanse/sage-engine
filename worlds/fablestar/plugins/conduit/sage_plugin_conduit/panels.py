"""Conduit's client panels: the attribute sheet (`stat_sheet`) and the skill tree (`tree`).

Data shapes are the engine's (sage.network.panels). The tree lists every domain with the leaves
the character has touched (a level, or a state other than raise); the full catalog stays behind
the `prof` and `bonus` commands, so the snapshot does not carry all leaves on every command.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .registry import ProficiencyRegistry
from .state_helpers import ATTRIBUTES_KEY, CONDUIT_KEY, total_proficiency_levels

ATTRIBUTES = ("FRT", "RFX", "ACU", "RSV", "PRS")
STATES = ("raise", "lower", "lock")
TONES = {"raise": "good", "lower": "warn"}


def _block(stats: dict[str, Any]) -> dict[str, Any]:
    block = stats.get(CONDUIT_KEY)
    return block if isinstance(block, dict) else {}


def attribute_sheet(
    stats: dict[str, Any], registry: ProficiencyRegistry, t: Callable[..., str]
) -> dict[str, Any]:
    attributes = _block(stats).get(ATTRIBUTES_KEY) or {}
    rows: list[dict[str, Any]] = [
        {"label": t(f"conduit.attribute.{key}"), "value": int(attributes.get(key, 10))}
        for key in ATTRIBUTES
    ]
    rows.append(
        {
            "label": t("conduit.label.resonance"),
            "value": total_proficiency_levels(dict(stats), registry=registry),
            "max": registry.total_level_cap(),
        }
    )
    return {"stats": rows}


def skill_tree(
    stats: dict[str, Any], registry: ProficiencyRegistry, t: Callable[..., str]
) -> dict[str, Any]:
    known = _block(stats).get("proficiencies") or {}
    domains: dict[str, dict[str, Any]] = {}
    for node_id in sorted(n for n in registry.nodes if "." not in n):
        node = registry.get_node(node_id)
        domains[node_id] = {"id": node_id, "label": node.name, "value": 0, "children": []}
    for leaf_id in registry.leaf_ids:
        row = known.get(leaf_id) or {}
        level = int(row.get("level", 0) or 0)
        state = row.get("state", "raise")
        if level <= 0 and state == "raise":
            continue
        node = registry.get_node(leaf_id)
        domain = domains.get(leaf_id.split(".")[0])
        if node is None or domain is None:
            continue
        leaf: dict[str, Any] = {
            "id": leaf_id,
            "label": node.name,
            "value": level,
            "max": registry.leaf_level_cap(),
            "note": t(
                "conduit.label.leaf_note",
                id=leaf_id,
                state=t(f"conduit.state.{state}"),
                peak=int(row.get("peak", level) or level),
            ),
            "actions": [
                {"label": t(f"conduit.state.{s}"), "command": f"{s} {leaf_id}"}
                for s in STATES
                if s != state
            ],
        }
        if state in TONES:
            leaf["tone"] = TONES[state]
        domain["children"].append(leaf)
        domain["value"] += level
    return {"nodes": list(domains.values()), "empty": t("conduit.label.no_skills")}
