"""Combat plugin — attack (deterministic damage, optional LLM narration) and flee.

Golden rule: math decides what happens, the LLM only colours it. The outcome line is always sent
first; prose follows if the narration backend answers.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from sage.api import EntityKilled, PluginAPI

logger = logging.getLogger(__name__)


def roll_damage(attacker_attack: int, defender_defense: int) -> int:
    """Deterministic damage roll: attack + d6 - defense, at least 1."""
    return max(1, attacker_attack + random.randint(1, 6) - defender_defense)


def setup(api: PluginAPI) -> None:
    api.ai.slot("narration")
    skills = list(api.param("skills", []) or [])
    flee_chance = float(api.param("flee_chance", 0.5))

    def service(name: str) -> Any:
        try:
            return api.services.get(name)
        except Exception:
            return None

    async def find_target(room_id: str, wanted: str) -> dict[str, Any] | None:
        for state in await api.rooms.entities(room_id):
            if state.get("alive", True) and (
                wanted in state.get("name", "").lower()
                or wanted in state.get("template", "").lower()
            ):
                return state
        return None

    def narrate(session: Any, facts: str) -> None:
        """Fire-and-forget prose; one pending narration per player, never for virtual sessions."""
        if (
            getattr(session, "virtual", False)
            or getattr(session, "combat_narration_pending", False)
            or not api.ai.enabled("narration")
        ):
            return
        session.combat_narration_pending = True

        async def run() -> None:
            try:
                prose = (await api.ai.narrate("narration", 200, narration_facts=facts)).strip()
                if prose:
                    await session.send(prose)
            except Exception as exc:
                logger.warning("Combat narration failed: %s", exc)
            finally:
                session.combat_narration_pending = False

        asyncio.get_running_loop().create_task(run())

    async def attack(session, args):
        """Attack an entity in the room. Usage: attack <target>"""
        player_id = session.player_id
        if not args:
            await session.send(api.t("combat.attack_what"))
            return
        wanted = " ".join(args).lower()
        room_id = await api.state.location(player_id)
        if not room_id:
            await session.send(api.t("combat.nowhere"))
            return
        target = await find_target(room_id, wanted)
        if target is None:
            await session.send(api.t("combat.no_target", wanted=wanted))
            return
        target_id = target["id"]

        equipment = service("equipment")
        kill_lines: list[str] = []
        counter_lines: list[str] = []
        ammo_note = None
        async with api.state.edit(player_id) as stats:
            attack_rating, defense_rating = api.resolvers.get("combat.ratings")(stats)
            if equipment is not None:
                gear_attack, gear_defense = equipment.bonuses(stats)
                attack_rating += gear_attack
                defense_rating += gear_defense
                lost, ammo_note = await equipment.fire(player_id, stats)
                attack_rating -= lost

            async with api.entities.lock(target_id):
                # Re-read under the lock: another attacker may have hit (or killed) it meanwhile.
                fresh = await api.entities.state(target_id)
                if fresh is None or not fresh.get("alive", True):
                    await session.send(api.t("combat.already_dead", name=target.get("name", "It")))
                    return
                target = fresh
                damage = roll_damage(attack_rating, int(target.get("defense", 0)))
                target["hp"] = int(target.get("hp", 1)) - damage
                dead = target["hp"] <= 0
                if dead:
                    target["alive"] = False
                await api.entities.save(target_id, target)

            counter_damage = 0
            if not dead:
                counter_damage = roll_damage(int(target.get("attack", 3)), defense_rating)
                stats["hp"] = max(0, int(stats.get("hp", 20)) - counter_damage)

            template_id = target.get("template", "")
            if dead:
                api.telemetry.event(
                    "kill",
                    killer=player_id,
                    virtual=bool(getattr(session, "virtual", False)),
                    template=template_id,
                    room=room_id,
                )
                await api.telemetry.heat("kills", room_id)
                await api.telemetry.heat(f"kills_by:{player_id}", template_id or "?")
            if int(stats.get("hp", 1)) <= 0:
                counter_lines += await api.characters.record_death(
                    session, player_id, stats, room_id, template_id
                )
            if dead:
                counter_lines += await api.counters.count(
                    player_id, stats, "kills", f"kills.{template_id}" if template_id else ""
                )
                # What the kill means (reputation, contracts, xp...) is up to subscribers.
                killed = EntityKilled(
                    killer_id=player_id,
                    entity_id=target_id,
                    template=template_id,
                    room_id=room_id,
                    faction=target.get("faction", ""),
                    stats=stats,
                )
                await api.events.publish(killed)
                kill_lines += killed.messages
            player_hp = int(stats.get("hp", 0))

        # Fighting is meaningful skill use (after the save, so the gain isn't overwritten).
        if skills:
            await api.progression.skill_used(player_id, random.choice(skills), 1.0)

        name = target.get("name", "the creature")
        facts = (
            f"Player attacks: {name}\n"
            f"Damage dealt: {damage}\n"
            f"Entity outcome: {'killed' if dead else 'wounded'}\n"
            f"Entity remaining HP: {max(0, target['hp'])}/{target.get('max_hp', '?')}\n"
        )
        if not dead:
            facts += f"Counter-attack damage: {counter_damage}\nPlayer remaining HP: {player_hp}\n"
        narrate(session, facts)

        if dead:
            await session.send(api.t("combat.strike_kill", name=name, damage=damage))
        else:
            await session.send(
                api.t("combat.hit_counter", name=name, damage=damage, counter=counter_damage)
            )
        if ammo_note:
            await session.send(ammo_note)
        if dead:
            dropped = await api.entities.kill(target_id, room_id)
            if dropped:
                items = ", ".join(i.get("name", "something") for i in dropped)
                await session.send(api.t("combat.drops", name=name, items=items))
            else:
                await session.send(api.t("combat.dead", name=name))
        for line in [*kill_lines, *counter_lines]:
            await session.send(line)
        if player_hp <= 0:
            await session.end("died", api.t("combat.slain"))

    async def flee(session, args):
        """Attempt to flee combat. Usage: flee"""
        player_id = session.player_id
        room_id = await api.state.location(player_id)
        if not room_id:
            return
        if not any(e.get("alive", True) for e in await api.rooms.entities(room_id)):
            await session.send(api.t("combat.flee_nothing"))
            return
        room = api.content.room(room_id)
        if not room or not room.exits:
            await session.send(api.t("combat.flee_nowhere"))
            return
        if random.random() < flee_chance:
            direction = random.choice(list(room.exits.keys()))
            await api.state.relocate(player_id, room.exits[direction].destination)
            await session.send(api.t("combat.flee_ok", direction=direction))
            await api.sessions.dispatch(session, "look")
        else:
            await session.send(api.t("combat.flee_fail"))

    api.commands.register("attack", attack, aliases=["a", "k", "kill", "hit"])
    api.commands.register("flee", flee, aliases=["run", "escape"])
