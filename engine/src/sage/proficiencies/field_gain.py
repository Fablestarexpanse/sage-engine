"""Best-effort field proficiency gain helper for command handlers."""

import logging
import random

logger = logging.getLogger(__name__)


async def try_field_gain_for_player(
    player_id: str,
    leaf_id: str,
    *,
    chance: float = 1.0,
    vr: bool = False,
) -> None:
    """Load player stats, attempt a field gain on `leaf_id`, and save. Never raises.

    chance: probability the attempt is made at all (gates spammy triggers like movement).
    """
    if chance < 1.0 and random.random() >= chance:
        return
    from sage.app import app_instance
    from sage.proficiencies.engine import ProficiencyEngine
    from sage.proficiencies.state_helpers import ensure_proficiency_block

    try:
        stats = await app_instance.redis.get_player_stats(player_id)
        ensure_proficiency_block(stats)
        eng = ProficiencyEngine(app_instance.content_loader.get_proficiency_registry())
        eng.try_field_gain(stats, leaf_id, vr=vr)
        await app_instance.redis.set_player_stats(player_id, stats)
    except Exception:
        logger.warning(
            "Field proficiency gain failed for %s (%s)", player_id, leaf_id, exc_info=True
        )


async def skill_used(player_id: str, skill: str, chance: float) -> None:
    """progression.skill_used provider: a skill id is a proficiency leaf."""
    await try_field_gain_for_player(player_id, skill, chance=chance)


def skill_level(stats: dict, skill: str) -> int:
    """progression.skill_level provider: the leaf's current level (0 when untrained)."""
    from sage.proficiencies.engine import ProficiencyEngine

    try:
        return ProficiencyEngine(None)._level(dict(stats), skill)
    except (TypeError, ValueError, AttributeError):
        return 0
