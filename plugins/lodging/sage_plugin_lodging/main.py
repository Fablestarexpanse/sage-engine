"""Lodging plugin: rent (or renew) a room at a rent desk; leases lapse unless renewed, so beds
circulate instead of being held forever."""

from __future__ import annotations

import asyncio
import json
import time

from sage.api import PluginAPI

from .leases import RENEW_WINDOW_S, RENTALS_KEY, LodgingModel, free_rooms, parse_rentals

HOME_ROOM = "home_room"
HOME_UNTIL = "home_until"
SWEEP_SECONDS = 60


class LodgingService:
    """What other systems (agents) may ask about rent desks and leases."""

    def __init__(self, api: PluginAPI):
        self._api = api

    def at(self, room_id: str | None) -> LodgingModel | None:
        if not room_id:
            return None
        room = self._api.content.room(room_id)
        return self._api.content.extension(room, "room", "lodging") if room else None

    async def rentals(self) -> dict[str, dict]:
        return parse_rentals(await self._api.redis.hgetall(RENTALS_KEY))

    free_rooms = staticmethod(free_rooms)

    def desk_for(self, room_ids: list[str], rented_room: str) -> str | None:
        """Which of these rooms is the desk that lets rented_room."""
        for room_id in room_ids:
            lodging = self.at(room_id)
            if lodging and rented_room in lodging.rooms:
                return room_id
        return None


def setup(api: PluginAPI) -> None:
    api.content.extend("room", "lodging", LodgingModel)
    api.state.block(HOME_ROOM, default=lambda: None)
    api.state.block(HOME_UNTIL, default=lambda: None)
    service = LodgingService(api)
    wallet = api.wallet
    # Read-check-write on the rentals hash must be serialized: agents tick concurrently, and
    # three of them once leased the same free bunk in one tick. One process, so a local lock.
    lease_lock = asyncio.Lock()

    async def expire_leases(now: float | None = None) -> list[tuple[str, str]]:
        """Drop lapsed leases and clear the tenant's home. Returns (room, tenant) pairs."""
        now = time.time() if now is None else now
        expired = []
        async with lease_lock:
            for room_id, lease in (await service.rentals()).items():
                if float(lease.get("until", 0)) > now:
                    continue
                tenant = lease.get("tenant", "")
                await api.redis.hdel(RENTALS_KEY, room_id)
                if tenant and (await api.state.snapshot(tenant)).get(HOME_ROOM) == room_id:
                    async with api.state.edit(tenant) as stats:
                        stats.pop(HOME_ROOM, None)
                        stats.pop(HOME_UNTIL, None)
                expired.append((room_id, tenant))
        for room_id, tenant in expired:
            api.telemetry.event("lease_expired", tenant=tenant, room=room_id)
        return expired

    async def sweep(tick: int) -> None:
        await expire_leases()

    async def rent(session, args) -> None:
        """Rent (or renew) a room at a rent desk. Usage: rent"""
        player_id = session.player_id
        desk_id = await api.state.location(player_id)
        lodging = service.at(desk_id)
        if lodging is None:
            await session.send(api.t("lodging.no_desk"))
            return
        async with lease_lock:
            await rent_locked(session, player_id, desk_id, lodging)

    async def rent_locked(session, player_id: str, desk_id: str, lodging: LodgingModel) -> None:
        now = time.time()
        rentals = await service.rentals()
        async with api.state.edit(player_id) as stats:
            home = stats.get(HOME_ROOM)
            home_lease = rentals.get(home) if home else None
            holds_home = bool(
                home_lease
                and home_lease.get("tenant") == player_id
                and float(home_lease.get("until", 0)) > now
            )
            if holds_home and home not in lodging.rooms:
                minutes = int((float(home_lease["until"]) - now) / 60)
                await session.send(api.t("lodging.elsewhere", home=home, minutes=minutes))
                return
            if holds_home:
                left = float(home_lease["until"]) - now
                if left > RENEW_WINDOW_S:
                    await session.send(
                        api.t("lodging.not_yet", room=home.split(":")[-1], minutes=int(left / 60))
                    )
                    return
                target, action = home, "renew"
            else:
                free = free_rooms(lodging, rentals, now)
                if not free:
                    soonest = min(
                        float(rentals.get(r, {}).get("until", now)) for r in lodging.rooms
                    )
                    await session.send(
                        api.t(
                            "lodging.full",
                            lodging=lodging.name,
                            minutes=max(1, int((soonest - now) / 60)),
                        )
                    )
                    return
                target, action = free[0], "rent"

            money = wallet.balance(stats)
            if not wallet.debit(stats, lodging.price):
                await session.send(
                    api.t(
                        "lodging.too_poor", price=lodging.price, currency=wallet.name(), money=money
                    )
                )
                return
            start = max(now, float(home_lease["until"])) if action == "renew" else now
            until = start + lodging.lease_minutes * 60
            stats[HOME_ROOM] = target
            stats[HOME_UNTIL] = int(until)
            rent_lines = await api.counters.count(player_id, stats, "rent_paid")
            await api.redis.hset(
                RENTALS_KEY, target, json.dumps({"tenant": player_id, "until": until})
            )
            money_left = wallet.balance(stats)

        api.telemetry.event(
            "rent", tenant=player_id, room=target, cost=lodging.price, action=action, desk=desk_id
        )
        await session.send(
            api.t(
                "lodging.renewed" if action == "renew" else "lodging.rented",
                room=target.split(":")[-1],
                minutes=lodging.lease_minutes,
                price=lodging.price,
                currency=wallet.name(),
                money=money_left,
            )
        )
        for line in rent_lines:
            await session.send(line)

    service.expire_leases = expire_leases
    api.commands.register("rent", rent)
    api.tick.every(SWEEP_SECONDS, sweep, name="lease_sweep")
    api.services.provide("lodging", service)
