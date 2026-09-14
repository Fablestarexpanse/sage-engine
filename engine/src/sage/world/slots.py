"""The engine's resolver slots with their defaults, in one place for servers and test hosts."""

from __future__ import annotations

from typing import Any

from sage.world import chargen, progression, ratings
from sage.world.death import default_death_check, default_respawn


def define_engine_slots(resolvers: Any) -> None:
    resolvers.define("death.check", default_death_check)
    resolvers.define("death.respawn", default_respawn)
    resolvers.define(progression.SKILL_USED, progression.default_skill_used)
    resolvers.define(progression.SKILL_LEVEL, progression.default_skill_level)
    resolvers.define(progression.SEED_ATTRIBUTES, progression.default_seed_attributes)
    resolvers.define(progression.TOTAL_LEVELS, progression.default_total_levels)
    resolvers.define(progression.SKILL_SHEET, progression.default_skill_sheet)
    resolvers.define(progression.PREPARE, progression.default_prepare)
    resolvers.define(chargen.VALIDATE, chargen.default_validate)
    resolvers.define(chargen.SEED, chargen.default_seed)
    resolvers.define(chargen.OPTIONS, chargen.default_options)
    resolvers.define(ratings.RATINGS, ratings.default_ratings)
