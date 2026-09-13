"""Search command — scavenge features that carry a search profile."""

import logging
import random
import uuid

from fablestar.commands.registry import command
from fablestar.network.session import Session

logger = logging.getLogger(__name__)

PERCEPTION_LEAF = "interface.perception.anomaly_scan"
# Each anomaly_scan level adds 0.5% find chance on top of the profile's base.
LEVEL_BONUS = 0.005
CHANCE_CAP = 0.95


def find_chance(base: float, perception_level: int) -> float:
    return min(CHANCE_CAP, base + max(0, perception_level) * LEVEL_BONUS)


def _perception_level(stats: dict) -> int:
    from fablestar.proficiencies.state_helpers import CONDUIT_KEY

    try:
        return int(stats[CONDUIT_KEY]["proficiencies"][PERCEPTION_LEAF]["level"])
    except (KeyError, TypeError, ValueError):
        return 0


@command("search", aliases=["scavenge", "loot"])
async def search(session: Session, args: list[str]):
    """Search a feature for useful items. Usage: search <feature>"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    if not args:
        await session.send("Search what? Usage: search <feature>")
        return

    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        await session.send("You are nowhere.")
        return
    room = app_instance.content_loader.get_room(room_id)
    if not room:
        await session.send("The world is collapsing around you.")
        return

    target = " ".join(args).lower()
    feature = None
    for f in room.features:
        haystack = [f.id.lower(), f.name.lower(), *[k.lower() for k in f.keywords]]
        if any(target in h for h in haystack):
            feature = f
            break
    if feature is None:
        await session.send(f"You see no '{target}' here to search.")
        return
    if feature.search is None:
        await session.send(f"You rummage through the {feature.name} but find nothing of interest.")
        return

    profile = feature.search
    found_so_far = await app_instance.redis.get_search_finds(room_id, feature.id)
    if found_so_far >= profile.max_finds:
        await session.send(f"The {feature.name} has been picked clean. Maybe later.")
        return

    stats = await app_instance.redis.get_player_stats(player_id)
    chance = find_chance(profile.chance, _perception_level(stats))

    # Searching is meaningful perception use either way (Epitaph TM pattern).
    from fablestar.proficiencies.field_gain import try_field_gain_for_player

    await try_field_gain_for_player(player_id, PERCEPTION_LEAF, chance=0.2)

    if random.random() > chance:
        await session.send(f"You search the {feature.name} but come up empty this time.")
        return

    template_id = random.choice(profile.items)
    template = app_instance.content_loader.get_item_template(template_id)
    if template is None:
        logger.error("Search profile on %s references unknown item %r", feature.id, template_id)
        await session.send(f"You search the {feature.name} but come up empty this time.")
        return

    inv = await app_instance.redis.get_player_inventory(player_id)
    inv.append(
        {
            "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
            "template": template.id,
            "name": template.name,
            "description": template.description,
            "value": template.value,
        }
    )
    await app_instance.redis.set_player_inventory(player_id, inv)
    await app_instance.redis.incr_search_finds(room_id, feature.id, profile.respawn_s)
    await session.send(f"Tucked away in the {feature.name}, you find: {template.name}.")

    # Achievement counter (best-effort; re-reads stats to include any field gain).
    try:
        from fablestar.achievements.engine import announcement, record_counter

        stats = await app_instance.redis.get_player_stats(player_id)
        registry = app_instance.content_loader.get_achievement_registry()
        granted = record_counter(stats, registry, "scavenged")
        await app_instance.redis.set_player_stats(player_id, stats)
        for ach in granted:
            await session.send(f"\r\n{announcement(ach)}")
    except Exception as exc:
        logger.warning("Scavenge achievement counter skipped: %s", exc)
