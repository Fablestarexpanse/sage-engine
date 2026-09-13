"""Rent command — take a room above the AIpub.

Rentals are a Redis hash (rentals: apartment_room_id -> tenant name). Renting
costs a flat fee from the stats-blob wallet and records home_room in stats,
so both players and agents can have a bed of their own. Sleeping (rest) in
your own room is handled by the rest/effects path plus agent feelings.
"""

import logging

from fablestar.commands.registry import command
from fablestar.network.session import Session

logger = logging.getLogger(__name__)

RENT_DESK_ROOMS = {"aipub:main_bar", "aipub:pub_entrance"}
RENTABLE_ROOMS = ["aipub:apartment_1", "aipub:apartment_2"]
RENT_COST_DIGI = 15
RENTALS_KEY = "rentals"


@command("rent")
async def rent(session: Session, args: list[str]):
    """Rent a room above the AIpub (ask at the bar). Usage: rent"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    room_id = await app_instance.redis.get_player_location(player_id)
    if room_id not in RENT_DESK_ROOMS:
        await session.send("Rooms are let at the AIpub bar — ask there.")
        return

    stats = await app_instance.redis.get_player_stats(player_id)
    if stats.get("home_room"):
        await session.send(f"You already keep a room: {stats['home_room']}.")
        return

    client = app_instance.redis.client
    taken = await client.hgetall(RENTALS_KEY)
    taken = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in (taken or {}).items()
    }
    free = next((r for r in RENTABLE_ROOMS if r not in taken), None)
    if free is None:
        await session.send("The barkeep shrugs: every room upstairs is taken.")
        return

    digi = int(stats.get("digi", 0) or 0)
    if digi < RENT_COST_DIGI:
        await session.send(
            f"A room runs {RENT_COST_DIGI} Digi; you carry {digi}. The barkeep waits."
        )
        return

    stats["digi"] = digi - RENT_COST_DIGI
    stats["home_room"] = free
    try:
        from fablestar.achievements.engine import record_counter

        record_counter(stats, app_instance.content_loader.get_achievement_registry(), "rent_paid")
    except Exception:
        logger.debug("rent counter skipped", exc_info=True)
    await client.hset(RENTALS_KEY, free, player_id)
    await app_instance.redis.set_player_stats(player_id, stats)
    slug = free.split(":")[-1]
    await session.send(
        f"The barkeep slides you a keycard: {slug}, upstairs. "
        f"{RENT_COST_DIGI} Digi, no refunds, no questions ({stats['digi']} left)."
    )
