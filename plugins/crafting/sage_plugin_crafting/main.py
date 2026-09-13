"""Crafting plugin: recipes, craft and deconstruct. Skill use is reported to the world's
progression by the skill ids the world maps item types to (params)."""

from __future__ import annotations

import uuid
from typing import Any

from sage.api import PluginAPI

from .rules import Recipe, Scraps, Yields, missing_for, scrap_yield


def setup(api: PluginAPI) -> None:
    api.content.extend("item", "recipe", Recipe)
    api.content.extend("item", "yields", Yields)
    api.content.extend("item", "scraps", Scraps)
    # World params: item type -> progression skill for crafting it, a fallback, and the
    # deconstruction skill. A world without progression leaves them unset.
    craft_skills: dict[str, str] = dict(api.param("skills", {}) or {})
    default_skill = api.param("default_skill", None)
    deconstruct_skill = api.param("deconstruct_skill", None)
    skill_chance = float(api.param("skill_chance", 0.6))

    def recipe(template: Any) -> dict[str, int]:
        claimed = api.content.extension(template, "item", "recipe")
        return dict(claimed.root) if claimed else {}

    def yields(template: Any) -> int:
        claimed = api.content.extension(template, "item", "yields")
        return claimed.root if claimed else 1

    def scraps(template: Any) -> dict[str, int]:
        claimed = api.content.extension(template, "item", "scraps")
        return dict(claimed.root) if claimed else {}

    def craftable() -> list[Any]:
        templates = (api.content.item_template(tid) for tid in api.content.item_template_ids())
        return sorted((t for t in templates if t and recipe(t)), key=lambda t: t.name)

    def part_names(parts: dict[str, int]) -> str:
        out = []
        for tid, n in parts.items():
            part = api.content.item_template(tid)
            out.append(api.t("crafting.part", count=n, name=part.name if part else tid))
        return ", ".join(out)

    def mint(template: Any) -> dict[str, Any]:
        return {
            "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
            "template": template.id,
            "name": template.name,
            "description": template.description,
            "value": template.value,
        }

    async def recipes(session, args) -> None:
        """List what you know how to craft. Usage: recipes"""
        inventory = await api.inventory.get(session.player_id)
        lines = [api.t("crafting.recipes_header")]
        for template in craftable():
            needs = recipe(template)
            batch = yields(template)
            lines.append(
                api.t(
                    "crafting.recipe_entry",
                    name=template.name,
                    batch=api.t("crafting.batch", count=batch) if batch > 1 else "",
                    parts=part_names(needs),
                    ready="" if missing_for(needs, inventory) else api.t("crafting.ready"),
                )
            )
        if len(lines) == 1:
            lines.append(api.t("crafting.no_recipes"))
        await session.send("\r\n".join(lines))

    async def craft(session, args) -> None:
        """Craft an item from parts you carry. Usage: craft <item>"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("crafting.craft_what"))
            return
        wanted = " ".join(args).lower()
        template = next(
            (t for t in craftable() if wanted in t.name.lower() or wanted in t.id), None
        )
        if template is None:
            await session.send(api.t("crafting.unknown_recipe", wanted=wanted))
            return
        needs = recipe(template)
        inventory = await api.inventory.get(player_id)
        gap = missing_for(needs, inventory)
        if gap:
            await session.send(api.t("crafting.still_need", parts=part_names(gap)))
            return

        async with api.state.edit(player_id) as stats:
            # Consume inputs (first matching instances), never equipped items.
            equipped = {
                (it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it
            }
            consumed: set[str] = set()
            for tid, n in needs.items():
                taken = 0
                for it in inventory:
                    if taken >= n:
                        break
                    if it.get("template") == tid and it.get("id") not in equipped | consumed:
                        consumed.add(it.get("id"))
                        taken += 1
                if taken < n:
                    await session.send(api.t("crafting.equipped_parts"))
                    return
            made = [mint(template) for _ in range(yields(template))]
            await api.inventory.set(
                player_id, [it for it in inventory if it.get("id") not in consumed] + made
            )
            lines = await api.counters.count(player_id, stats, "crafted", f"crafted.{template.id}")
        await api.progression.skill_used(
            player_id, craft_skills.get(template.type, default_skill), chance=skill_chance
        )
        api.telemetry.event("craft", actor=player_id, item=template.id, count=len(made))
        await session.send(
            api.t(
                "crafting.crafted",
                item=template.name,
                count=f" x{len(made)}" if len(made) > 1 else "",
            )
        )
        for line in lines:
            await session.send(line)

    async def deconstruct(session, args) -> None:
        """Break an item down into parts. Usage: deconstruct <item>"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("crafting.deconstruct_what"))
            return
        wanted = " ".join(args).lower()
        async with api.state.edit(player_id) as stats:
            inventory = await api.inventory.get(player_id)
            equipped = {
                (it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it
            }
            item = next(
                (
                    it
                    for it in inventory
                    if wanted in it.get("name", "").lower() and it.get("id") not in equipped
                ),
                None,
            )
            if item is None:
                await session.send(api.t("crafting.no_spare", wanted=wanted))
                return
            template = api.content.item_template(item.get("template", ""))
            if template is None:
                await session.send(api.t("crafting.doesnt_come_apart"))
                return
            outputs = scrap_yield(recipe(template), scraps(template))
            if not outputs:
                await session.send(api.t("crafting.nothing_useful", item=template.name))
                return
            remaining = [it for it in inventory if it.get("id") != item.get("id")]
            made: dict[str, int] = {}
            for tid, n in outputs.items():
                part = api.content.item_template(tid)
                if part is None:
                    continue
                remaining.extend(mint(part) for _ in range(n))
                made[tid] = n
            await api.inventory.set(player_id, remaining)
            lines = await api.counters.count(player_id, stats, "deconstructed")
        await api.progression.skill_used(player_id, deconstruct_skill, chance=skill_chance)
        api.telemetry.event("deconstruct", actor=player_id, item=template.id)
        await session.send(
            api.t("crafting.deconstructed", item=template.name, parts=part_names(made))
        )
        for line in lines:
            await session.send(line)

    api.commands.register("recipes", recipes, aliases=["craftable"])
    api.commands.register("craft", craft, aliases=["make", "assemble"])
    api.commands.register("deconstruct", deconstruct, aliases=["dismantle", "breakdown"])
