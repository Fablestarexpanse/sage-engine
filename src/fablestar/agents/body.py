"""
Agent Body — the zero-LLM reflex layer.

Every body tick picks ONE action by fixed priority and issues it as a plain
command string through the dispatcher (agents can do nothing a player can't):

  1. flee     — hp below 30%: run for an exit
  2. fight    — a living hostile entity shares the room: attack it
  3. eat      — hurt below 60% and carrying a consumable: use it
  4. rest     — hurt in a safe-type room: rest (the effects engine heals)
  5. goal     — continue the current goal script (list of queued commands)
  6. wander   — routine loop: move one step toward the next routine room
  7. idle     — nothing (most ticks end here via the wander cooldown)

Pure decision function + tiny context dataclass so tests need no server.
"""

import random
from dataclasses import dataclass, field
from typing import Any

FLEE_HP_FRACTION = 0.30
EAT_HP_FRACTION = 0.60
WANDER_COOLDOWN_S = (18.0, 45.0)


@dataclass
class BodyContext:
    hp: int
    max_hp: int
    room_type: str
    exits: list[str]
    hostiles: list[str]  # names of living hostile entities in the room
    consumables: list[str]  # names of carried heal>0 items
    resting: bool
    goal_commands: list[str] = field(default_factory=list)
    next_routine_direction: str | None = None
    wander_ready: bool = True
    in_buying_shop: bool = False  # this room's shop buys goods
    sellable_count: int = 0  # unequipped items with value > 0
    hungry: bool = False  # hunger need past threshold


def decide(ctx: BodyContext, rng: random.Random | None = None) -> tuple[str, str | None]:
    """Return (reason, command | None). None = idle this tick."""
    rng = rng or random.Random()
    hp_frac = ctx.hp / max(1, ctx.max_hp)

    if ctx.hostiles and hp_frac < FLEE_HP_FRACTION and ctx.exits:
        return ("flee", rng.choice(ctx.exits))
    if ctx.hostiles:
        return ("fight", f"attack {ctx.hostiles[0]}")
    if (hp_frac < EAT_HP_FRACTION or ctx.hungry) and ctx.consumables:
        return ("eat", f"use {ctx.consumables[0]}")
    if hp_frac < 1.0 and ctx.room_type == "safe" and not ctx.resting:
        return ("rest", "rest")
    # Merchant instinct: standing in a shop that buys while carrying goods.
    if ctx.in_buying_shop and ctx.sellable_count > 0:
        return ("sell", "sell all")
    if ctx.goal_commands:
        return ("goal", ctx.goal_commands[0])
    if ctx.next_routine_direction and ctx.wander_ready:
        return ("wander", ctx.next_routine_direction)
    return ("idle", None)


def route_step(
    current_room: str,
    target_room: str,
    exits_of: dict[str, dict[str, str]],
    max_depth: int = 24,
) -> str | None:
    """
    BFS one step toward target: returns the direction to take from
    current_room, or None when unreachable/already there. `exits_of` maps
    room_id -> {direction: destination_room_id}.
    """
    if current_room == target_room:
        return None
    seen = {current_room}
    queue: list[tuple[str, str, int]] = []  # (first_step_direction, room, depth)
    for direction, dest in exits_of.get(current_room, {}).items():
        if dest not in seen:
            seen.add(dest)
            queue.append((direction, dest, 1))
    i = 0
    while i < len(queue):
        first_direction, node, depth = queue[i]
        i += 1
        if node == target_room:
            return first_direction
        if depth >= max_depth:
            continue
        for _, nxt in exits_of.get(node, {}).items():
            if nxt not in seen:
                seen.add(nxt)
                queue.append((first_direction, nxt, depth + 1))
    return None


def route_path(
    current_room: str,
    target_room: str,
    exits_of: dict[str, dict[str, str]],
    max_depth: int = 24,
) -> list[str] | None:
    """Full BFS direction list from current to target; None when unreachable."""
    if current_room == target_room:
        return []
    seen = {current_room}
    queue: list[tuple[list[str], str, int]] = []
    for direction, dest in exits_of.get(current_room, {}).items():
        if dest not in seen:
            seen.add(dest)
            queue.append(([direction], dest, 1))
    i = 0
    while i < len(queue):
        path, node, depth = queue[i]
        i += 1
        if node == target_room:
            return path
        if depth >= max_depth:
            continue
        for direction, nxt in exits_of.get(node, {}).items():
            if nxt not in seen:
                seen.add(nxt)
                queue.append(([*path, direction], nxt, depth + 1))
    return None


def hostiles_in(entities: list[dict[str, Any]], tags_of) -> list[str]:
    """Names of living entities whose template carries the 'hostile' tag."""
    out = []
    for e in entities:
        if not e.get("alive", True):
            continue
        tags = tags_of(e.get("template", "")) or set()
        if "hostile" in tags:
            out.append(e.get("name", e.get("template", "something")))
    return out
