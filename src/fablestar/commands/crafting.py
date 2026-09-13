"""Crafting commands — craft from recipes, deconstruct back to parts.

Recipes live on ItemTemplate (recipe: inputs, yields: batch size, scraps:
deconstruct outputs). Deterministic: exact inputs in, exact outputs out;
proficiency gains use the fabrication tree like combat uses combat.
"""

import logging
import uuid

from fablestar.commands.registry import command
from fablestar.network.session import Session

logger = logging.getLogger(__name__)

CRAFT_GAIN_LEAVES = {
    "weapon": "fabrication.weaponsmithing.energy_weapons",
    "armor": "fabrication.armorcraft.plating",
    "ammo": "fabrication.devices.utility_tools",
}
DECONSTRUCT_LEAF = "fabrication.salvage.disassembly"


def missing_for(recipe: dict[str, int], inventory: list[dict]) -> dict[str, int]:
    """What the recipe still needs given this inventory (empty = craftable)."""
    have: dict[str, int] = {}
    for it in inventory:
        t = it.get("template", "")
        have[t] = have.get(t, 0) + 1
    return {t: n - have.get(t, 0) for t, n in recipe.items() if have.get(t, 0) < n}


def scrap_yield(template) -> dict[str, int]:
    """Deconstruction outputs: explicit scraps, else half the recipe."""
    if template.scraps:
        return dict(template.scraps)
    if template.recipe:
        out = {t: n // 2 for t, n in template.recipe.items() if n // 2 > 0}
        if not out:  # never scrap into nothing when a recipe exists
            first = next(iter(template.recipe))
            out = {first: 1}
        return out
    return {}


def _mint(template) -> dict:
    return {
        "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
        "template": template.id,
        "name": template.name,
        "description": template.description,
        "value": template.value,
    }


def _craftable_templates(loader):
    out = []
    for tid in loader.list_item_template_ids():
        tmpl = loader.get_item_template(tid)
        if tmpl and tmpl.recipe:
            out.append(tmpl)
    return sorted(out, key=lambda t: t.name)


async def _fabrication_gain(player_id: str, leaf: str) -> None:
    try:
        from fablestar.proficiencies.field_gain import try_field_gain_for_player

        await try_field_gain_for_player(player_id, leaf, chance=0.6)
    except Exception:
        logger.debug("fabrication gain skipped", exc_info=True)


@command("recipes", aliases=["craftable"])
async def recipes(session: Session, args: list[str]):
    """List what you know how to craft. Usage: recipes"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    inv = await app_instance.redis.get_player_inventory(player_id)
    lines = ["Craftable (craft <item>):"]
    for tmpl in _craftable_templates(app_instance.content_loader):
        parts = []
        for t, n in tmpl.recipe.items():
            part = app_instance.content_loader.get_item_template(t)
            parts.append(f"{n}x {part.name if part else t}")
        gap = missing_for(tmpl.recipe, inv)
        ready = "" if gap else "  [ready]"
        batch = f" (makes {tmpl.yields})" if tmpl.yields > 1 else ""
        lines.append(f"  {tmpl.name}{batch} — {', '.join(parts)}{ready}")
    if len(lines) == 1:
        lines.append("  nothing — no recipes are written down yet.")
    await session.send("\r\n".join(lines))


@command("craft", aliases=["make", "assemble"])
async def craft(session: Session, args: list[str]):
    """Craft an item from parts you carry. Usage: craft <item>"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    if not args:
        await session.send("Craft what? 'recipes' lists what you can make.")
        return

    wanted = " ".join(args).lower()
    tmpl = next(
        (
            t
            for t in _craftable_templates(app_instance.content_loader)
            if wanted in t.name.lower() or wanted in t.id
        ),
        None,
    )
    if tmpl is None:
        await session.send(f"You don't know how to craft '{wanted}'. Try 'recipes'.")
        return

    inv = await app_instance.redis.get_player_inventory(player_id)
    gap = missing_for(tmpl.recipe, inv)
    if gap:
        needs = []
        for t, n in gap.items():
            part = app_instance.content_loader.get_item_template(t)
            needs.append(f"{n}x {part.name if part else t}")
        await session.send(f"You still need: {', '.join(needs)}.")
        return

    # Consume inputs (first matching instances), never equipped items.
    stats = await app_instance.redis.get_player_stats(player_id)
    equipped_ids = {(it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it}
    consumed_ids: set[str] = set()
    for t, n in tmpl.recipe.items():
        taken = 0
        for it in inv:
            if taken >= n:
                break
            if it.get("template") == t and it.get("id") not in equipped_ids | consumed_ids:
                consumed_ids.add(it.get("id"))
                taken += 1
        if taken < n:
            await session.send("Your equipped gear doesn't count as spare parts.")
            return

    new_inv = [it for it in inv if it.get("id") not in consumed_ids]
    made = [_mint(tmpl) for _ in range(max(1, tmpl.yields))]
    new_inv.extend(made)
    await app_instance.redis.set_player_inventory(player_id, new_inv)

    granted = []
    try:
        from fablestar.achievements.engine import record_counter

        registry = app_instance.content_loader.get_achievement_registry()
        granted += record_counter(stats, registry, "crafted")
        granted += record_counter(stats, registry, f"crafted.{tmpl.id}")
    except Exception:
        logger.debug("craft counter skipped", exc_info=True)
    await app_instance.redis.set_player_stats(player_id, stats)
    await _fabrication_gain(
        player_id, CRAFT_GAIN_LEAVES.get(tmpl.type, "fabrication.materials.composites")
    )

    count_note = f" x{len(made)}" if len(made) > 1 else ""
    await session.send(f"You assemble: {tmpl.name}{count_note}.")
    from fablestar.achievements.engine import announcement

    for ach in granted:
        await session.send(announcement(ach))


@command("deconstruct", aliases=["dismantle", "breakdown"])
async def deconstruct(session: Session, args: list[str]):
    """Break an item down into parts. Usage: deconstruct <item>"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return
    if not args:
        await session.send("Deconstruct what? Usage: deconstruct <item>")
        return

    wanted = " ".join(args).lower()
    inv = await app_instance.redis.get_player_inventory(player_id)
    stats = await app_instance.redis.get_player_stats(player_id)
    equipped_ids = {(it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it}

    item = next(
        (
            it
            for it in inv
            if wanted in it.get("name", "").lower() and it.get("id") not in equipped_ids
        ),
        None,
    )
    if item is None:
        await session.send(f"You aren't carrying a spare '{wanted}' (equipped gear doesn't count).")
        return
    tmpl = app_instance.content_loader.get_item_template(item.get("template", ""))
    if tmpl is None:
        await session.send("Whatever that is, it doesn't come apart.")
        return
    outputs = scrap_yield(tmpl)
    if not outputs:
        await session.send(f"The {tmpl.name} doesn't break down into anything useful.")
        return

    new_inv = [it for it in inv if it.get("id") != item.get("id")]
    made_names = []
    for t, n in outputs.items():
        part = app_instance.content_loader.get_item_template(t)
        if part is None:
            continue
        for _ in range(n):
            new_inv.append(_mint(part))
        made_names.append(f"{n}x {part.name}")
    await app_instance.redis.set_player_inventory(player_id, new_inv)

    granted = []
    try:
        from fablestar.achievements.engine import record_counter

        registry = app_instance.content_loader.get_achievement_registry()
        granted += record_counter(stats, registry, "deconstructed")
    except Exception:
        logger.debug("deconstruct counter skipped", exc_info=True)
    await app_instance.redis.set_player_stats(player_id, stats)
    await _fabrication_gain(player_id, DECONSTRUCT_LEAF)

    await session.send(f"You strip the {tmpl.name} down to: {', '.join(made_names)}.")
    from fablestar.achievements.engine import announcement

    for ach in granted:
        await session.send(announcement(ach))
