"""Equipment plugin: wear weapons and armor in the world's slots; gear adds attack/defense and
may consume ammo when fighting."""

from __future__ import annotations

from typing import Any

from pydantic import RootModel

from sage.api import PluginAPI

from .rules import EQUIPMENT_KEY, ensure_equipment, equip_item, equipment_bonuses, unequip_slot


class Slot(RootModel[str]):
    """`slot:` — which equipment slot the item is worn in."""


class Bonus(RootModel[int]):
    """`attack:` / `defense:` — flat bonus while worn."""


class Ammo(RootModel[str]):
    """`ammo:` — item template consumed per attack; without a round the attack bonus is lost."""


class EquipmentService:
    """What other plugins (combat, agents) use: slots, bonuses, firing, equipping."""

    def __init__(self, api: PluginAPI, slots: list[str]):
        self.api = api
        self.slots = slots

    def _field(self, template: Any, name: str) -> Any:
        claimed = self.api.content.extension(template, "item", name) if template else None
        return claimed.root if claimed is not None else None

    def slot_of(self, template: Any) -> str | None:
        return self._field(template, "slot")

    def bonuses_of(self, template_id: str) -> tuple[int, int]:
        template = self.api.content.item_template(template_id)
        return int(self._field(template, "attack") or 0), int(self._field(template, "defense") or 0)

    def bonuses(self, stats: dict[str, Any]) -> tuple[int, int]:
        return equipment_bonuses(stats, self.bonuses_of)

    def equip(
        self,
        stats: dict[str, Any],
        inventory: list[dict[str, Any]],
        item: dict[str, Any],
        template: Any,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Wear item (message, new inventory) — for plugins seeding characters (agents)."""
        slot, new_inventory, previous = equip_item(
            stats, inventory, item, self.slot_of(template), self.slots
        )
        if slot is None:
            return self.api.t("equipment.cant_equip", item=item.get("name", "item")), inventory
        return self._equipped_message(item, slot, previous), new_inventory

    def _equipped_message(self, item: dict[str, Any], slot: str, previous: Any) -> str:
        if previous:
            return self.api.t(
                "equipment.equipped_swap",
                item=item.get("name", "item"),
                slot=slot,
                previous=previous.get("name", "old gear"),
            )
        return self.api.t("equipment.equipped", item=item.get("name", "item"), slot=slot)

    async def fire(self, player_id: str, stats: dict[str, Any]) -> tuple[int, str | None]:
        """Consume one round for each worn ammo-fed item. Returns (attack lost, note for player)."""
        lost, note = 0, None
        for item in ensure_equipment(stats).values():
            template = self.api.content.item_template((item or {}).get("template", ""))
            ammo = self._field(template, "ammo")
            if not ammo:
                continue
            inventory = await self.api.inventory.get(player_id)
            round_item = next((it for it in inventory if it.get("template") == ammo), None)
            ammo_template = self.api.content.item_template(ammo)
            ammo_name = ammo_template.name if ammo_template else ammo
            if round_item is None:
                lost += int(self._field(template, "attack") or 0)
                note = self.api.t("equipment.ammo_empty", item=template.name, ammo=ammo_name)
                continue
            remaining = [it for it in inventory if it.get("id") != round_item.get("id")]
            await self.api.inventory.set(player_id, remaining)
            if not any(it.get("template") == ammo for it in remaining):
                note = self.api.t("equipment.ammo_last", ammo=ammo_name)
        return lost, note


def setup(api: PluginAPI) -> None:
    api.content.extend("item", "slot", Slot)
    api.content.extend("item", "attack", Bonus)
    api.content.extend("item", "defense", Bonus)
    api.content.extend("item", "ammo", Ammo)
    api.state.block(EQUIPMENT_KEY)
    slots = list(api.world.manifest.content.equipment_slots or []) or ["weapon", "armor"]
    service = EquipmentService(api, slots)

    def find(inventory: list[dict[str, Any]], args: list[str]) -> dict[str, Any] | None:
        wanted = " ".join(args).lower()
        return next((it for it in inventory if wanted in it.get("name", "").lower()), None)

    async def equip(session, args):
        """Equip a weapon or armor from your inventory. Usage: equip <item>"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("equipment.equip_what"))
            return
        inventory = await api.inventory.get(player_id)
        item = find(inventory, args)
        if item is None:
            await session.send(api.t("equipment.not_carrying", wanted=" ".join(args).lower()))
            return
        template = api.content.item_template(item.get("template", ""))
        async with api.state.edit(player_id) as stats:
            slot, new_inventory, previous = equip_item(
                stats, inventory, item, service.slot_of(template), slots
            )
        if slot is None:
            await session.send(api.t("equipment.cant_equip", item=item.get("name", "item")))
            return
        await api.inventory.set(player_id, new_inventory)
        await session.send(service._equipped_message(item, slot, previous))

    async def unequip(session, args):
        """Remove equipped gear. Usage: unequip <slot|item name>"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("equipment.unequip_what", slots="|".join(slots)))
            return
        inventory = await api.inventory.get(player_id)
        async with api.state.edit(player_id) as stats:
            item, new_inventory = unequip_slot(stats, inventory, " ".join(args), slots)
        if item is None:
            await session.send(api.t("equipment.nothing_equipped"))
            return
        await api.inventory.set(player_id, new_inventory)
        await session.send(api.t("equipment.unequipped", item=item.get("name", "item")))

    async def gear(session, args):
        """Show what you have equipped. Usage: gear"""
        equipment = ensure_equipment(await api.state.snapshot(session.player_id))
        lines = [api.t("equipment.header")]
        for slot in slots:
            item = equipment.get(slot)
            name = item.get("name") if item else api.t("equipment.empty_slot")
            lines.append(api.t("equipment.slot_line", slot=slot, item=name))
        await session.send("\r\n".join(lines))

    api.commands.register("equip", equip, aliases=["wield", "wear"])
    api.commands.register("unequip", unequip, aliases=["remove", "stow"])
    api.commands.register("gear", gear, aliases=["equipment", "equipped"])
    api.services.provide("equipment", service)
