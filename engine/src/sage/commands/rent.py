"""Rent command — timed leases on rooms let from a rent desk.

A desk is any room with a `lodging` block (the AIpub bar lets the upstairs
apartments; the Tidewater Bunkhouse lets bunks). Leases live in the Redis
hash `rentals` as room_id -> {"tenant", "until"} and mirror to the tenant's
stats as home_room / home_until. Leases lapse unless renewed — renting again
at the same desk while you hold a room there extends it — so beds circulate
instead of being held forever.
"""

import asyncio
import json
import logging
import time

from sage.commands.registry import command
from sage.network.session import Session

logger = logging.getLogger(__name__)

RENTALS_KEY = "rentals"
RENEW_WINDOW_S = 15 * 60  # renewing is allowed once a lease has < 15 min left
# Read-check-write on the rentals hash must be serialized: agents tick
# concurrently, and three of them once leased the same free bunk in one tick.
# Single-process server, so an in-process lock is sufficient.
_lease_lock = asyncio.Lock()


def _decode(v) -> str:
    return v.decode() if isinstance(v, bytes) else v


async def read_rentals(redis) -> dict[str, dict]:
    """room_id -> {"tenant": str, "until": float}. Legacy plain values read as expired."""
    raw = await redis.client.hgetall(RENTALS_KEY)
    out = {}
    for k, v in (raw or {}).items():
        v = _decode(v)
        try:
            lease = json.loads(v)
            if not isinstance(lease, dict):
                raise ValueError
        except ValueError:
            lease = {"tenant": v, "until": 0}
        out[_decode(k)] = lease
    return out


def free_rooms(lodging, rentals: dict[str, dict], now: float) -> list[str]:
    """Rooms in this lodging with no lease or a lapsed one."""
    return [r for r in lodging.rooms if float(rentals.get(r, {}).get("until", 0)) <= now]


async def expire_leases(redis, now: float | None = None) -> list[tuple[str, str]]:
    """Drop lapsed leases and clear the tenant's home. Returns (room, tenant) pairs."""
    now = time.time() if now is None else now
    expired = []
    for room_id, lease in (await read_rentals(redis)).items():
        if float(lease.get("until", 0)) > now:
            continue
        tenant = lease.get("tenant", "")
        await redis.client.hdel(RENTALS_KEY, room_id)
        if tenant:
            try:
                stats = await redis.get_player_stats(tenant)
                if stats and stats.get("home_room") == room_id:
                    stats.pop("home_room", None)
                    stats.pop("home_until", None)
                    await redis.set_player_stats(tenant, stats)
            except Exception:
                logger.debug("lease expiry: tenant stats update failed", exc_info=True)
        expired.append((room_id, tenant))
    if expired:
        from sage.telemetry import log_event

        for room_id, tenant in expired:
            log_event("lease_expired", tenant=tenant, room=room_id)
    return expired


@command("rent")
async def rent(session: Session, args: list[str]):
    """Rent (or renew) a room at a rent desk — the AIpub bar or the bunkhouse. Usage: rent"""
    from sage.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    room_id = await app_instance.redis.get_player_location(player_id)
    desk = app_instance.content_loader.get_room(room_id) if room_id else None
    lodging = desk.lodging if desk else None
    if lodging is None:
        await session.send("Nobody lets rooms here. Try the AIpub bar or the Tidewater Bunkhouse.")
        return

    async with _lease_lock:
        await _rent_locked(session, player_id, room_id, lodging)


async def _rent_locked(session: Session, player_id: str, room_id: str, lodging) -> None:
    from sage.app import app_instance

    now = time.time()
    redis = app_instance.redis
    rentals = await read_rentals(redis)
    stats = await redis.get_player_stats(player_id)
    wallet = app_instance.wallet
    money = wallet.balance(stats)
    home = stats.get("home_room")
    home_lease = rentals.get(home) if home else None
    holds_home = bool(
        home_lease
        and home_lease.get("tenant") == player_id
        and float(home_lease.get("until", 0)) > now
    )

    if holds_home and home not in lodging.rooms:
        mins = int((float(home_lease["until"]) - now) / 60)
        await session.send(f"You already keep a room elsewhere ({home}, {mins} min left).")
        return

    if holds_home:
        left = float(home_lease["until"]) - now
        if left > RENEW_WINDOW_S:
            await session.send(
                f"Your lease on {home.split(':')[-1]} runs another {int(left / 60)} minutes. "
                "Come back when it's nearly up."
            )
            return
        target, action = home, "renew"
    else:
        free = free_rooms(lodging, rentals, now)
        if not free:
            soonest = min(float(rentals.get(r, {}).get("until", now)) for r in lodging.rooms)
            await session.send(
                f"{lodging.name} is full. A bed frees up in about "
                f"{max(1, int((soonest - now) / 60))} minutes."
            )
            return
        target, action = free[0], "rent"

    if not wallet.debit(stats, lodging.price):
        await session.send(f"A room here runs {lodging.price} {wallet.name()}; you carry {money}.")
        return

    start = max(now, float(home_lease["until"])) if action == "renew" else now
    until = start + lodging.lease_minutes * 60
    stats["home_room"] = target
    stats["home_until"] = int(until)
    from sage.world.counters import count

    rent_lines = await count(app_instance, player_id, stats, "rent_paid")
    await redis.client.hset(RENTALS_KEY, target, json.dumps({"tenant": player_id, "until": until}))
    await redis.set_player_stats(player_id, stats)

    from sage.telemetry import log_event

    log_event(
        "rent", tenant=player_id, room=target, cost=lodging.price, action=action, desk=room_id
    )
    slug = target.split(":")[-1]
    verb = "extends your lease on" if action == "renew" else "hands you the key to"
    await session.send(
        f"The keeper {verb} {slug} — {lodging.lease_minutes} minutes for {lodging.price} {wallet.name()} "
        f"({wallet.balance(stats)} left)."
    )
    for line in rent_lines:
        await session.send(line)
