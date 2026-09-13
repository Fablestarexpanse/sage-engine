"""Factions plugin: reputation from kills, generated contracts, and the commands for both."""

from __future__ import annotations

from typing import Any

from sage.api import EntityKilled, PluginAPI

from .missions import (
    MISSION_KEY,
    active_mission,
    describe_mission,
    generate_mission,
    record_kill,
    try_complete_collect,
    will_deal,
)
from .registry import FactionRegistry, load_factions
from .standing import FACTIONS_KEY, apply_kill_reputation, standings_lines


class FactionsService:
    """What other plugins (agents) may ask about factions, through api.services."""

    def __init__(self, cache: Any):
        self._cache = cache

    def registry(self) -> FactionRegistry:
        return self._cache.get()

    active_mission = staticmethod(active_mission)
    will_deal = staticmethod(will_deal)


def setup(api: PluginAPI) -> None:
    api.state.block(FACTIONS_KEY)
    api.state.block(MISSION_KEY, default=lambda: None)
    cache = api.content.cached("factions", load_factions)

    async def on_kill(event: EntityKilled) -> None:
        registry = cache.get()
        event.messages.extend(
            apply_kill_reputation(event.stats, registry, event.template, event.faction)
        )
        lines, completed = record_kill(event.stats, registry, event.template, api.wallet)
        event.messages.extend(lines)
        if completed:
            event.messages.extend(
                await api.counters.count(event.killer_id, event.stats, "missions_completed")
            )

    async def factions(session, args) -> None:
        """Show your faction standings. Usage: factions"""
        registry = cache.get()
        if not registry.all():
            await session.send(api.t("factions.none"))
            return
        stats = await api.state.snapshot(session.player_id)
        await session.send(
            "\r\n".join([api.t("factions.header"), *standings_lines(stats, registry)])
        )

    async def missions(session, args) -> None:
        """Faction contracts. Usage: missions [accept <faction> | complete | abandon]"""
        player_id = session.player_id
        registry = cache.get()
        stats = await api.state.snapshot(player_id)
        sub = args[0] if args else ""

        if sub == "accept":
            if active_mission(stats):
                await session.send(api.t("factions.mission.busy"))
                return
            needle = " ".join(args[1:]).lower()
            faction = next(
                (
                    f
                    for f in registry.all()
                    if f.offers_missions() and (needle in f.id.lower() or needle in f.name.lower())
                ),
                None,
            )
            if not needle or faction is None:
                await session.send(api.t("factions.mission.accept_usage"))
                return
            if not will_deal(stats, faction):
                await session.send(api.t("factions.mission.refused", faction=faction.name))
                return
            mission = generate_mission(faction)
            if mission is None:
                await session.send(api.t("factions.mission.no_work", faction=faction.name))
                return
            await api.state.set(player_id, MISSION_KEY, mission)
            await session.send(
                api.t("factions.mission.accepted", mission=describe_mission(mission, registry))
            )
            return

        if sub == "abandon":
            if not active_mission(stats):
                await session.send(api.t("factions.mission.none_active"))
                return
            await api.state.set(player_id, MISSION_KEY, None)
            await session.send(api.t("factions.mission.abandoned"))
            return

        if sub == "complete":
            # Paying out touches the wallet and counters too, so edit the whole character.
            async with api.state.edit(player_id) as live:
                inventory = await api.inventory.get(player_id)
                messages, new_inventory = try_complete_collect(
                    live, registry, inventory, api.wallet
                )
                if new_inventory is not None:
                    await api.inventory.set(player_id, new_inventory)
                    messages += await api.counters.count(player_id, live, "missions_completed")
            await session.send("\r\n".join(messages))
            return

        # Default view: active mission + who is hiring.
        lines = []
        mission = active_mission(stats)
        if mission:
            lines.append(
                api.t("factions.mission.active", mission=describe_mission(mission, registry))
            )
            if mission.get("kind") == "collect":
                lines.append(api.t("factions.mission.deliver_hint"))
        else:
            lines.append(api.t("factions.mission.idle"))
        hiring = [f for f in registry.all() if f.offers_missions() and will_deal(stats, f)]
        if hiring:
            lines.append(api.t("factions.mission.hiring", names=", ".join(f.name for f in hiring)))
            lines.append(api.t("factions.mission.accept_hint"))
        await session.send("\r\n".join(lines))

    api.events.subscribe(EntityKilled, on_kill)
    api.commands.register("factions", factions, aliases=["rep", "reputation"])
    api.commands.register("missions", missions, aliases=["mission"])
    api.services.provide("factions", FactionsService(cache))
