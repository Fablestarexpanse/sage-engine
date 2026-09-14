"""Consumables plugin: `use` an item with a `heal:` value to restore health."""

from __future__ import annotations

from typing import Any

from pydantic import Field, RootModel

from sage.api import PluginAPI


class Heal(RootModel[int]):
    """`heal:` — health restored when the item is used up."""

    root: int = Field(ge=0)


class ConsumablesService:
    def __init__(self, api: PluginAPI):
        self.api = api

    def heal_of(self, template: Any) -> int:
        claimed = self.api.content.extension(template, "item", "heal") if template else None
        return int(claimed.root) if claimed is not None else 0


def setup(api: PluginAPI) -> None:
    api.content.extend("item", "heal", Heal)
    service = ConsumablesService(api)

    async def use(session, args):
        """Use a consumable from your inventory. Usage: use <item>"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("consumables.use_what"))
            return
        wanted = " ".join(args).lower()
        inventory = await api.inventory.get(player_id)
        item = next((it for it in inventory if wanted in it.get("name", "").lower()), None)
        if item is None:
            await session.send(api.t("consumables.not_carrying", wanted=wanted))
            return
        template = api.content.item_template(item.get("template", ""))
        heal = service.heal_of(template)
        if heal <= 0:
            await session.send(api.t("consumables.cant_use", item=item.get("name", "item")))
            return
        current = await api.state.snapshot(player_id)
        if int(current.get("hp", 0)) >= int(current.get("max_hp", current.get("hp", 20))):
            # Nothing to restore: keep the item instead of spending it for +0.
            await session.send(api.t("consumables.already_whole", item=item.get("name", "item")))
            return
        async with api.state.edit(player_id) as stats:
            max_hp = int(stats.get("max_hp", stats.get("hp", 20)))
            before = int(stats.get("hp", 0))
            stats["hp"] = min(max_hp, before + heal)
            # Usage tracking: totals + per template, so "most used item" is answerable.
            lines = await api.counters.count(
                player_id, stats, "items_used", f"items_used.{template.id}"
            )
            hp = stats["hp"]
        await api.inventory.set(
            player_id, [it for it in inventory if it.get("id") != item.get("id")]
        )
        await session.send(
            api.t(
                "consumables.consumed",
                item=item.get("name", "item"),
                gained=hp - before,
                hp=hp,
                max_hp=max_hp,
            )
        )
        for line in lines:
            await session.send(line)

    api.commands.register("use", use, aliases=["eat", "consume", "drink"])
    api.services.provide("consumables", service)
