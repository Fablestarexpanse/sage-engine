"""Resolver-slot providers backed by the proficiency system while it is still engine code.

They move into the world plugin that owns proficiencies (phase-3 plan 3.10); engine callers only
ever reach this system through the slots.
"""

from __future__ import annotations

from typing import Any

from sage.world import chargen, progression, ratings


def provide_all(resolvers: Any, server: Any) -> None:
    from sage.proficiencies.field_gain import skill_level, skill_used
    from sage.proficiencies.starter import (
        apply_starter_to_stats,
        coerce_starter_level,
        validate_starter_allocation,
    )
    from sage.proficiencies.state_helpers import (
        combat_attack_defense_from_stats,
        ensure_proficiency_block,
        migrate_legacy_stats,
        seed_attributes,
        skill_sheet,
        total_levels,
    )

    def registry():
        return server.content_loader.get_proficiency_registry()

    def prepare(stats: dict[str, Any]) -> dict[str, Any]:
        out = migrate_legacy_stats(dict(stats or {}))
        ensure_proficiency_block(out)
        return out

    def combat_ratings(stats: dict[str, Any]) -> tuple[int, int]:
        hybrid = bool(getattr(server.config.server, "proficiency_combat_hybrid", True))
        return combat_attack_defense_from_stats(stats, hybrid_legacy=hybrid)

    def validate(choices: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        """choices {"proficiencies": {leaf: level}} -> cleaned allocation (whole numbers)."""
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
            ok, err = validate_starter_allocation(cleaned, registry())
            if not ok:
                return err, {}
        return None, cleaned

    def seed(stats: dict[str, Any], cleaned: dict[str, Any]) -> None:
        ensure_proficiency_block(stats)
        if cleaned:
            apply_starter_to_stats(stats, cleaned, registry())

    for slot, fn in (
        (progression.SKILL_USED, skill_used),
        (progression.SKILL_LEVEL, skill_level),
        (progression.SEED_ATTRIBUTES, seed_attributes),
        (progression.TOTAL_LEVELS, total_levels),
        (progression.SKILL_SHEET, skill_sheet),
        (progression.PREPARE, prepare),
        (ratings.RATINGS, combat_ratings),
        (chargen.VALIDATE, validate),
        (chargen.SEED, seed),
    ):
        resolvers.provide(slot, fn, owner="proficiencies")
