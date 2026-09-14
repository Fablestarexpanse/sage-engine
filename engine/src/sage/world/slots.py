"""The engine's resolver slots with their defaults, in one place for servers and test hosts."""

from __future__ import annotations

from typing import Any

from sage.world import chargen, progression, ratings
from sage.world.death import default_death_check, default_respawn


def define_engine_slots(resolvers: Any, world: Any = None) -> None:
    """Define every engine slot. With a world, chargen defaults follow its stats.yaml."""
    resolvers.define("death.check", default_death_check)
    resolvers.define("death.respawn", default_respawn)
    resolvers.define(progression.SKILL_USED, progression.default_skill_used)
    resolvers.define(progression.SKILL_LEVEL, progression.default_skill_level)
    resolvers.define(progression.SEED_ATTRIBUTES, progression.default_seed_attributes)
    resolvers.define(progression.TOTAL_LEVELS, progression.default_total_levels)
    resolvers.define(progression.SKILL_SHEET, progression.default_skill_sheet)
    resolvers.define(progression.PREPARE, progression.default_prepare)
    validate, seed, options = (
        chargen.default_validate,
        chargen.default_seed,
        chargen.default_options,
    )
    schema = getattr(world, "stats", None)
    if schema is not None and schema.attributes and schema.chargen.attribute_points:
        validate, seed, options = chargen.attribute_point_buy(
            schema, lambda stats, spread: resolvers.get(progression.SEED_ATTRIBUTES)(stats, spread)
        )
    resolvers.define(chargen.VALIDATE, validate)
    resolvers.define(chargen.SEED, seed)
    resolvers.define(chargen.OPTIONS, options)
    resolvers.define(ratings.RATINGS, ratings.default_ratings)
