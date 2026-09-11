"""Combat commands — attack (with proficiency damage and LLM narration) and flee."""

import asyncio
import logging
import random

from fablestar.commands.registry import command
from fablestar.network.session import Session

logger = logging.getLogger(__name__)

# Per-entity locks so two players attacking the same target can't interleave
# the read-modify-write of its Redis state (lost HP updates / double kills).
# Single-process server, so an in-process asyncio.Lock is sufficient.
_entity_locks: dict[str, asyncio.Lock] = {}


def _entity_lock(entity_id: str) -> asyncio.Lock:
    lock = _entity_locks.get(entity_id)
    if lock is None:
        lock = _entity_locks[entity_id] = asyncio.Lock()
    return lock


def discard_entity_lock(entity_id: str) -> None:
    """Drop the lock for an entity leaving the world (called from spawner despawn)."""
    _entity_locks.pop(entity_id, None)


def _roll_damage(attacker_attack: int, defender_defense: int) -> int:
    """Deterministic damage roll. LLMs describe what happened; math decides it."""
    roll = random.randint(1, 6)
    raw = attacker_attack + roll - defender_defense
    return max(1, raw)


@command("attack", aliases=["a", "kill", "hit"])
async def attack(session: Session, args: list[str]):
    """Attack an entity in the room. Usage: attack <target>"""
    from fablestar.app import app_instance

    if not args:
        await session.send("Attack what? Usage: attack <target>")
        return

    player_id = session.player_id
    if not player_id:
        return

    target_name = " ".join(args).lower()
    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        await session.send("You are nowhere.")
        return

    # Find matching entity in room
    entity_ids = await app_instance.redis.get_room_entities(room_id)
    target_state = None
    target_id = None
    for eid in entity_ids:
        state = await app_instance.redis.get_entity_state(eid)
        if state and state.get("alive", True):
            if (
                target_name in state.get("name", "").lower()
                or target_name in state.get("template", "").lower()
            ):
                target_state = state
                target_id = eid
                break

    if target_state is None or target_id is None:
        await session.send(f"You see no '{target_name}' here to attack.")
        return

    # --- Player attacks entity ---
    from fablestar.proficiencies.engine import ProficiencyEngine
    from fablestar.proficiencies.state_helpers import (
        combat_attack_defense_from_stats,
        ensure_proficiency_block,
    )

    player_stats = await app_instance.redis.get_player_stats(player_id)
    ensure_proficiency_block(player_stats)
    hybrid = bool(app_instance.config.server.proficiency_combat_hybrid)
    player_attack, player_defense_rating = combat_attack_defense_from_stats(
        player_stats, hybrid_legacy=hybrid
    )

    async with _entity_lock(target_id):
        # Re-read under the lock: another attacker may have hit (or killed)
        # the target between the room search above and now.
        fresh = await app_instance.redis.get_entity_state(target_id)
        if fresh is None or not fresh.get("alive", True):
            await session.send(f"{target_state.get('name', 'It')} is already dead.")
            return
        target_state = fresh
        damage_dealt = _roll_damage(player_attack, target_state.get("defense", 0))
        target_state["hp"] = target_state.get("hp", 1) - damage_dealt
        entity_dead = target_state["hp"] <= 0
        if entity_dead:
            target_state["alive"] = False
        await app_instance.redis.set_entity_state(target_id, target_state)

    # --- Entity counter-attacks (if still alive) ---
    counter_damage = 0
    if not entity_dead:
        entity_attack = target_state.get("attack", 3)
        counter_damage = _roll_damage(entity_attack, player_defense_rating)
        player_stats["hp"] = max(0, player_stats.get("hp", 20) - counter_damage)

    # Field proficiency: meaningful combat use (best-effort; roll may fail).
    try:
        eng = ProficiencyEngine(app_instance.content_loader.get_proficiency_registry())
        pool = [
            "combat.melee.blades",
            "combat.melee.impact",
            "combat.ballistic.sidearms",
            "combat.tactics.threat_assessment",
        ]
        eng.try_field_gain(player_stats, random.choice(pool), vr=False)
    except Exception as exc:
        logger.warning("Combat proficiency gain skipped: %s", exc)

    await app_instance.redis.set_player_stats(player_id, player_stats)

    # --- LLM narrates the exchange ---
    entity_name = target_state.get("name", "the creature")
    outcome = "killed" if entity_dead else "wounded"
    narration_facts = (
        f"Player attacks: {entity_name}\n"
        f"Damage dealt: {damage_dealt}\n"
        f"Entity outcome: {outcome}\n"
        f"Entity remaining HP: {max(0, target_state['hp'])}/{target_state.get('max_hp', '?')}\n"
    )
    if not entity_dead:
        narration_facts += (
            f"Counter-attack damage: {counter_damage}\n"
            f"Player remaining HP: {player_stats.get('hp', 0)}\n"
        )

    try:
        prompt = app_instance.prompt_manager.render(
            "combat_narration",
            narration_facts=narration_facts,
        )
        narration = await app_instance.llm_client.generate(prompt, max_tokens=200)
    except Exception as e:
        logger.warning(f"Combat narration failed: {e}")
        if entity_dead:
            narration = f"You strike {entity_name} for {damage_dealt} damage. It falls."
        else:
            narration = (
                f"You hit {entity_name} for {damage_dealt} damage. "
                f"It strikes back for {counter_damage}."
            )

    await session.send(f"\r\n{narration}")

    # --- Post-combat cleanup ---
    if entity_dead:
        # kill_entity → despawn_entity discards the per-entity lock
        dropped = await app_instance.spawner.kill_entity(target_id, room_id)
        if dropped:
            drop_names = []
            for iid in dropped:
                istate = await app_instance.redis.get_item_state(iid)
                if istate:
                    drop_names.append(istate.get("name", "something"))
            if drop_names:
                await session.send(f"{entity_name} drops: {', '.join(drop_names)}.")
        else:
            await session.send(f"{entity_name} is dead.")

    if player_stats.get("hp", 1) <= 0:
        await session.send("\r\nYou have been slain. Disconnecting...")
        await session.close()


@command("flee", aliases=["run", "escape"])
async def flee(session: Session, args: list[str]):
    """Attempt to flee combat. Usage: flee"""
    from fablestar.app import app_instance

    player_id = session.player_id
    if not player_id:
        return

    room_id = await app_instance.redis.get_player_location(player_id)
    if not room_id:
        return

    room = app_instance.content_loader.get_room(room_id)
    if not room or not room.exits:
        await session.send("There is nowhere to flee!")
        return

    # 50% chance to escape
    if random.random() < 0.5:
        direction = random.choice(list(room.exits.keys()))
        target_room_id = room.exits[direction].destination
        await app_instance.redis.set_player_location(player_id, target_room_id)
        await session.send(f"You flee {direction}!")
        await app_instance.dispatcher.dispatch(session, "look")
    else:
        await session.send("You fail to escape!")
