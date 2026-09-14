"""Conduit: Fablestar's progression. Five attributes (FRT/RFX/ACU/RSV/PRS), a 278-leaf
proficiency tree gained by use, the chargen skill allocation, and combat ratings derived from
both. Everything reaches the engine through resolver slots, commands and routes."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from sage.api import PluginAPI, t

from . import commands, panels, routes
from .catalog_loader import load_proficiency_catalog_from_disk
from .engine import ProficiencyEngine
from .registry import ProficiencyRegistry
from .starter import (
    STARTER_MAX_PER_LEAF,
    STARTER_POINTS_BUDGET,
    apply_starter_to_stats,
    catalog_leaves_for_client,
    coerce_starter_level,
    validate_starter_allocation,
)
from .state_helpers import (
    CONDUIT_KEY,
    combat_attack_defense_from_stats,
    ensure_proficiency_block,
    migrate_legacy_stats,
    seed_attributes,
    skill_sheet,
    total_levels,
)


def _load_registry(proficiencies_dir: Path) -> ProficiencyRegistry:
    return ProficiencyRegistry(load_proficiency_catalog_from_disk(proficiencies_dir.parent).leaves)


def clean_allocation(
    choices: dict[str, Any], registry: ProficiencyRegistry
) -> tuple[str | None, dict[str, int]]:
    """chargen choices {"proficiencies": {leaf: level}} -> cleaned whole-number allocation."""
    cleaned: dict[str, int] = {}
    seen: set[str] = set()
    for key, value in dict((choices or {}).get("proficiencies") or {}).items():
        if not isinstance(key, str) or not key.strip():
            continue
        leaf = key.strip()
        if leaf in seen:  # " a.b" and "a.b" both given
            return "invalid_starter_proficiencies", {}
        seen.add(leaf)
        level = coerce_starter_level(value)
        if level is None:
            return "invalid_starter_proficiencies", {}
        if level != 0:
            cleaned[leaf] = level
    if cleaned:
        ok, err = validate_starter_allocation(cleaned, registry)
        if not ok:
            return err, {}
    return None, cleaned


def setup(api: PluginAPI) -> None:
    api.state.block(CONDUIT_KEY)
    catalog = api.content.cached("proficiencies", _load_registry, pattern="*.*")
    hybrid = bool(api.param("combat_hybrid", True))

    def prepare(stats: dict[str, Any]) -> dict[str, Any]:
        out = migrate_legacy_stats(dict(stats or {}))
        ensure_proficiency_block(out)
        return out

    async def skill_used(player_id: str, skill: str, chance: float) -> None:
        if chance < 1.0 and random.random() >= chance:
            return
        try:
            async with api.state.edit(player_id) as stats:
                ensure_proficiency_block(stats)
                ProficiencyEngine(catalog.get()).try_field_gain(stats, skill, vr=False)
        except Exception:
            api.log.warning(
                "Field proficiency gain failed for %s (%s)", player_id, skill, exc_info=True
            )

    def skill_level(stats: dict[str, Any], skill: str) -> int:
        try:
            return ProficiencyEngine(None)._level(dict(stats), skill)
        except (TypeError, ValueError, AttributeError):
            return 0

    def ratings(stats: dict[str, Any]) -> tuple[int, int]:
        return combat_attack_defense_from_stats(stats, hybrid_legacy=hybrid)

    def validate(choices: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        return clean_allocation(choices, catalog.get())

    def seed(stats: dict[str, Any], cleaned: dict[str, Any]) -> None:
        ensure_proficiency_block(stats)
        if cleaned:
            apply_starter_to_stats(stats, cleaned, catalog.get())

    def options() -> dict[str, Any]:
        """The chargen skill picker: leaves with detail text, point budget and per-leaf cap."""
        leaves = catalog_leaves_for_client(catalog.get())
        return {
            "kind": "skill_points",
            "title": t("conduit.chargen.title"),
            "budget": STARTER_POINTS_BUDGET,
            "max_per_leaf": STARTER_MAX_PER_LEAF,
            "domains": sorted({x["domain"] for x in leaves}),
            "leaves": leaves,
        }

    for slot, fn in (
        ("progression.skill_used", skill_used),
        ("progression.skill_level", skill_level),
        ("progression.seed_attributes", seed_attributes),
        ("progression.total_levels", total_levels),
        ("progression.skill_sheet", skill_sheet),
        ("progression.prepare", prepare),
        ("combat.ratings", ratings),
        ("chargen.validate", validate),
        ("chargen.seed", seed),
        ("chargen.options", options),
    ):
        api.resolvers.provide(slot, fn)

    commands.register(api, catalog.get)
    routes.mount(api, catalog)
    api.snapshot.contribute(
        "conduit", lambda name, stats: panels.attribute_sheet(stats, catalog.get(), api.t)
    )
    api.snapshot.contribute(
        "conduit_skills", lambda name, stats: panels.skill_tree(stats, catalog.get(), api.t)
    )
    api.ui.panel("attributes", "stat_sheet", "conduit", icon="◈")
    api.ui.panel("skills", "tree", "conduit_skills", icon="◇")
