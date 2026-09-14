"""Effects plugin: effect ticks on the game loop, plus `effects` and `rest`."""

from __future__ import annotations

import logging

from sage.api import PluginAPI

logger = logging.getLogger(__name__)

CHECK_SECONDS = 2.0


def setup(api: PluginAPI) -> None:
    rest_room_types = set(api.param("rest_room_types", ["safe"]) or [])
    rest_heal = int(api.param("rest_heal", 2))
    rest_seconds = float(api.param("rest_seconds", 30.0))

    async def advance_all(tick: int) -> None:
        for player_id in api.sessions.online():
            try:
                messages, lines, died = await api.effects.advance(player_id)
            except Exception as exc:
                logger.warning("Effect processing failed for %s: %s", player_id, exc)
                continue
            session = api.sessions.get(player_id)
            if session is None or not (messages or lines or died):
                continue
            for line in [*messages, *lines]:
                await session.send(line)
            await api.sessions.push_snapshot(session)
            if died:
                await session.end("died", api.t("effects.succumbed"))

    async def effects(session, args):
        """Show active effects on you. Usage: effects"""
        lines = api.effects.describe(await api.state.snapshot(session.player_id))
        if not lines:
            await session.send(api.t("effects.none"))
            return
        await session.send("\r\n".join([api.t("effects.header"), *lines]))

    async def rest(session, args):
        """Rest to recover health — only somewhere safe. Usage: rest"""
        player_id = session.player_id
        room_id = await api.state.location(player_id)
        room = api.content.room(room_id) if room_id else None
        if room is None or room.type not in rest_room_types:
            await session.send(api.t("effects.rest_unsafe"))
            return
        async with api.state.edit(player_id) as stats:
            if int(stats.get("hp", 0)) >= int(stats.get("max_hp", stats.get("hp", 1))):
                await session.send(api.t("effects.rest_whole"))
                return
            if api.effects.find(stats, "body.resting"):
                await session.send(api.t("effects.rest_already"))
                return
            api.effects.apply(
                stats,
                api.effects.make(
                    "body.resting",
                    name="resting",
                    description=api.t("effects.rest_effect"),
                    kind="hot",
                    magnitude=rest_heal,
                    interval=5.0,
                    duration=rest_seconds,
                    debuff=False,
                ),
            )
        await session.send(api.t("effects.rest_start"))

    api.tick.every(CHECK_SECONDS, advance_all, name="effects")
    api.commands.register("effects", effects, aliases=["buffs", "debuffs"])
    api.commands.register("rest", rest, aliases=["sleep", "recover"])
