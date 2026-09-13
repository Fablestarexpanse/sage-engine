"""
AgentManager — spawns agent bodies and drives their reflex ticks.

Agents are full citizens of the session layer: registered in SessionManager,
present in Redis room sets, acting only via dispatcher-dispatched command
strings. M1 scope: spawn from personas, wander routines, fight/flee/eat/rest
reflexes. Brains (LLM) arrive in M3/M4; restart/give/teleport admin hooks
land in M2 but the manager API for them lives here from the start.
"""

import logging
import random
import time
import uuid
from typing import TYPE_CHECKING, Any

from fablestar.agents.body import (
    WANDER_COOLDOWN_S,
    BodyContext,
    decide,
    hostiles_in,
    route_step,
)
from fablestar.agents.models import AgentPersonaModel
from fablestar.agents.session import AgentSession

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)

AGENT_TICK_INTERVAL = 8  # 4 Hz tick → body decisions every 2 s (staggered)


class AgentState:
    def __init__(self, persona: AgentPersonaModel, session: AgentSession):
        self.persona = persona
        self.session = session
        self.routine_idx = 0
        self.next_wander_at = 0.0
        self.goal_commands: list[str] = []
        self.goal_label: str | None = None
        self.last_action: str = "spawned"
        self.last_action_at: float = time.time()
        self.rng = random.Random(hash(persona.id) & 0xFFFF)


class AgentManager:
    def __init__(self, server: "FablestarServer"):
        self.server = server
        self.agents: dict[str, AgentState] = {}  # persona.id -> state
        self._spawned = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def spawn_all(self):
        registry = self.server.content_loader.get_agent_registry()
        for persona in registry.all():
            if persona.enabled and persona.id not in self.agents:
                try:
                    await self.spawn(persona)
                except Exception as exc:
                    logger.error("Agent %s failed to spawn: %s", persona.id, exc)
        self._spawned = True

    async def spawn(self, persona: AgentPersonaModel):
        session = AgentSession(persona.id, persona.name)
        sm = self.server.session_manager
        sm.sessions[session.id] = session
        sm.player_to_session[persona.name] = session.id

        stats: dict[str, Any] = dict(persona.stats)
        stats.setdefault("max_hp", stats.get("hp", 60))
        stats.setdefault("hp", stats["max_hp"])
        stats["is_agent"] = True

        inventory: list[dict[str, Any]] = []
        # Equip persona gear (slot -> template id) through the equipment engine.
        from fablestar.items.equipment import equip_item

        for template_id in persona.gear.values():
            template = self.server.content_loader.get_item_template(template_id)
            if template is None:
                logger.warning("Agent %s gear %r unknown", persona.id, template_id)
                continue
            item = {
                "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
                "template": template.id,
                "name": template.name,
                "description": template.description,
                "value": template.value,
            }
            _, inventory = equip_item(stats, [*inventory, item], item, template)

        await self.server.redis.set_player_stats(persona.name, stats)
        await self.server.redis.set_player_inventory(persona.name, inventory)
        await self.server.redis.set_player_location(persona.name, persona.spawn_room)

        self.agents[persona.id] = AgentState(persona, session)
        logger.info("Agent spawned: %s (%s) in %s", persona.name, persona.id, persona.spawn_room)

    async def despawn(self, agent_id: str):
        state = self.agents.pop(agent_id, None)
        if state is None:
            return
        name = state.persona.name
        room_id = await self.server.redis.get_player_location(name)
        if room_id:
            await self.server.redis.remove_player_from_room(name, room_id)
        sm = self.server.session_manager
        sm.player_to_session.pop(name, None)
        sm.sessions.pop(state.session.id, None)
        logger.info("Agent despawned: %s", name)

    async def restart(self, agent_id: str):
        """Despawn and respawn from the (possibly edited) persona on disk."""
        await self.despawn(agent_id)
        registry = self.server.content_loader.get_agent_registry()
        persona = registry.get(agent_id)
        if persona and persona.enabled:
            await self.spawn(persona)

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    async def on_tick(self, tick_count: int):
        if not self._spawned:
            await self.spawn_all()
        if tick_count % AGENT_TICK_INTERVAL != 0:
            return
        for agent_id in list(self.agents):
            try:
                await self._tick_agent(self.agents[agent_id])
            except Exception as exc:
                logger.warning("Agent tick failed for %s: %s", agent_id, exc)

    async def _tick_agent(self, state: AgentState):
        server = self.server
        name = state.persona.name
        room_id = await server.redis.get_player_location(name)
        if not room_id:
            return
        room = server.content_loader.get_room(room_id)
        if room is None:
            return
        stats = await server.redis.get_player_stats(name)

        # Entities + hostility
        entity_states = []
        for eid in await server.redis.get_room_entities(room_id):
            es = await server.redis.get_entity_state(eid)
            if es:
                entity_states.append(es)

        def tags_of(template_id: str):
            tmpl = server.content_loader.get_entity_template(template_id)
            return tmpl.tags if tmpl else set()

        inventory = await server.redis.get_player_inventory(name)
        consumables = []
        for it in inventory:
            tmpl = server.content_loader.get_item_template(it.get("template", ""))
            if tmpl and tmpl.heal > 0:
                consumables.append(it.get("name", tmpl.name))

        from fablestar.effects.engine import find_effects

        now = time.time()
        ctx = BodyContext(
            hp=int(stats.get("hp", 1)),
            max_hp=int(stats.get("max_hp", 1)),
            room_type=room.type,
            exits=list(room.exits.keys()),
            hostiles=hostiles_in(entity_states, tags_of),
            consumables=consumables,
            resting=bool(find_effects(stats, "body.resting")),
            goal_commands=list(state.goal_commands),
            next_routine_direction=self._routine_direction(state, room_id),
            wander_ready=now >= state.next_wander_at,
        )
        reason, command = decide(ctx, state.rng)
        if command is None:
            return
        if reason == "goal" and state.goal_commands:
            state.goal_commands.pop(0)
            if not state.goal_commands:
                state.goal_label = None
        if reason == "wander":
            lo, hi = WANDER_COOLDOWN_S
            state.next_wander_at = now + state.rng.uniform(lo, hi)
        state.last_action = f"{reason}: {command}"
        state.last_action_at = now
        await server.dispatcher.dispatch(state.session, command)

    # ------------------------------------------------------------------
    # Routine navigation
    # ------------------------------------------------------------------

    def _routine_direction(self, state: AgentState, current_room: str) -> str | None:
        routine = state.persona.routine
        if not routine:
            return None
        zone = state.persona.spawn_zone()
        target = routine[state.routine_idx % len(routine)]
        target_id = target if ":" in target else f"{zone}:{target}"
        if target_id == current_room:
            state.routine_idx = (state.routine_idx + 1) % len(routine)
            target = routine[state.routine_idx]
            target_id = target if ":" in target else f"{zone}:{target}"
            if target_id == current_room:
                return None
        return route_step(current_room, target_id, self._exits_map(zone))

    def _exits_map(self, zone: str) -> dict[str, dict[str, str]]:
        """room_id -> {direction: destination} for a zone, walked via the loader."""
        cache_key = f"agents:exits:{zone}"
        cached = self.server.content_loader._cache.get(cache_key)
        if cached is not None:
            return cached
        exits_of: dict[str, dict[str, str]] = {}
        # BFS outward from every known agent anchor in this zone.
        seeds = [
            p.spawn_room
            for p in self.server.content_loader.get_agent_registry().all()
            if p.spawn_zone() == zone
        ]
        queue = list(dict.fromkeys(seeds))
        seen = set(queue)
        while queue:
            room_id = queue.pop()
            room = self.server.content_loader.get_room(room_id)
            if room is None:
                continue
            exits_of[room_id] = {d: ex.destination for d, ex in room.exits.items()}
            for dest in exits_of[room_id].values():
                if dest not in seen:
                    seen.add(dest)
                    queue.append(dest)
        self.server.content_loader._cache[cache_key] = exits_of
        return exits_of
