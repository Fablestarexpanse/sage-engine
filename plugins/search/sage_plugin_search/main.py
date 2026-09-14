"""Search plugin: scavenge room features that carry a search profile."""

from __future__ import annotations

import random
import uuid
from typing import Any

from sage.api import PluginAPI

from .rules import SearchModel, find_chance, finds_key


class SearchService:
    """What other systems (agents) may ask about searchable features."""

    def __init__(self, api: PluginAPI):
        self._api = api

    def profile(self, feature: Any) -> SearchModel | None:
        return self._api.content.extension(feature, "feature", "search")

    def room_yielding(self, room_ids: list[str], template_id: str) -> str | None:
        """The first of these rooms with a feature whose search can turn up template_id."""
        for room_id in room_ids:
            room = self._api.content.room(room_id)
            for feature in room.features if room else []:
                profile = self.profile(feature)
                if profile and template_id in profile.items:
                    return room_id
        return None


def setup(api: PluginAPI) -> None:
    api.content.extend("feature", "search", SearchModel)
    service = SearchService(api)
    # The world's search skill (a progression skill id) and its find-chance bonus per level.
    skill = api.param("skill", None)
    per_level = float(api.param("skill_bonus_per_level", 0.005))

    async def search(session, args) -> None:
        """Search a feature for useful items. Usage: search <feature>"""
        player_id = session.player_id
        room_id = await api.state.location(player_id)
        room = api.content.room(room_id) if room_id else None
        if room is None:
            await session.send(api.t("search.nowhere"))
            return

        if args:
            target = " ".join(args).lower()
            feature = next(
                (
                    f
                    for f in room.features
                    if any(
                        target in h
                        for h in [f.id.lower(), f.name.lower(), *[k.lower() for k in f.keywords]]
                    )
                ),
                None,
            )
            if feature is None:
                await session.send(api.t("search.no_target", target=target))
                return
            if service.profile(feature) is None:
                await session.send(api.t("search.nothing_of_interest", feature=feature.name))
                return
        else:
            # Bare 'search' sweeps the room's first searchable feature (what agents issue).
            feature = next((f for f in room.features if service.profile(f) is not None), None)
            if feature is None:
                await session.send(api.t("search.nothing_here"))
                return

        profile = service.profile(feature)
        key = finds_key(room_id, feature.id)
        if int(await api.redis.get(key) or 0) >= profile.max_finds:
            await session.send(api.t("search.picked_clean", feature=feature.name))
            return

        stats = await api.state.snapshot(player_id)
        chance = find_chance(profile.chance, api.progression.skill_level(stats, skill), per_level)
        # Searching is meaningful skill use whether or not anything turns up.
        await api.progression.skill_used(player_id, skill, chance=0.2)

        if random.random() > chance:
            await session.send(api.t("search.empty", feature=feature.name))
            return
        template_id = random.choice(profile.items)
        template = api.content.item_template(template_id)
        if template is None:
            api.log.error(
                "Search profile on %s references unknown item %r", feature.id, template_id
            )
            await session.send(api.t("search.empty", feature=feature.name))
            return

        inventory = await api.inventory.get(player_id)
        inventory.append(
            {
                "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
                "template": template.id,
                "name": template.name,
                "description": template.description,
                "value": template.value,
            }
        )
        await api.inventory.set(player_id, inventory)
        # Count the find; the counter expires so the feature restocks itself.
        if await api.redis.incrby(key, 1) == 1:
            await api.redis.expire(key, int(profile.respawn_s))
        await session.send(api.t("search.found", feature=feature.name, item=template.name))

        async with api.state.edit(player_id) as live:
            lines = await api.counters.count(player_id, live, "scavenged")
        for line in lines:
            await session.send(line)

    api.commands.register("search", search, aliases=["scavenge", "loot"])
    api.services.provide("search", service)
