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
        self.last_hp: int | None = None
        self.enabled = True
        # POV log for the admin "look through their eyes" panel (brain fills
        # real prompts in M3/M4; body decisions land here meanwhile).
        self.pov: list[dict[str, Any]] = []
        self.rng = random.Random(hash(persona.id) & 0xFFFF)


class AgentManager:
    def __init__(self, server: "FablestarServer"):
        self.server = server
        self.agents: dict[str, AgentState] = {}  # persona.id -> state
        self._spawned = False
        self._brain = None  # lazy: config not fully loaded at construction

    @property
    def brain(self):
        if self._brain is None:
            from fablestar.agents.brain import AgentBrain

            self._brain = AgentBrain(self.server)
        return self._brain

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

        # Durable state wins over the persona seed (memories/feelings/gear
        # survive server restarts); admin restart deletes the row first.
        row = await self._load_row(persona.id)
        if row is not None:
            stats = dict(row["stats"])
            stats["is_agent"] = True
            inventory = list(row["inventory"])
            room_id = row["room_id"]
            if self.server.content_loader.get_room(room_id) is None:
                room_id = persona.spawn_room
        else:
            stats = dict(persona.stats)
            stats.setdefault("max_hp", stats.get("hp", 60))
            stats.setdefault("hp", stats["max_hp"])
            stats["is_agent"] = True
            # Agents are computer-controlled players: same conduit attribute
            # and proficiency blocks, so they level through the same engine.
            from fablestar.proficiencies.state_helpers import ensure_proficiency_block

            ensure_proficiency_block(stats)
            stats.setdefault("counters", {})

            inventory = []
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
            room_id = persona.spawn_room

        await self.server.redis.set_player_stats(persona.name, stats)
        await self.server.redis.set_player_inventory(persona.name, inventory)
        await self.server.redis.set_player_location(persona.name, room_id)

        self.agents[persona.id] = AgentState(persona, session)
        logger.info(
            "Agent spawned: %s (%s) in %s%s",
            persona.name,
            persona.id,
            room_id,
            " [restored]" if row is not None else "",
        )

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
        """Reset: drop durable state and respawn fresh from the persona on disk."""
        await self.despawn(agent_id)
        await self._delete_row(agent_id)
        registry = self.server.content_loader.get_agent_registry()
        persona = registry.get(agent_id)
        if persona and persona.enabled:
            await self.spawn(persona)

    # ------------------------------------------------------------------
    # Durability (agent_state table; flushed on the persistence cadence)
    # ------------------------------------------------------------------

    async def _load_row(self, persona_id: str) -> dict[str, Any] | None:
        try:
            from sqlalchemy import select

            from fablestar.state.models import AgentState as AgentStateRow

            async with self.server.db.session_factory() as db:
                result = await db.execute(
                    select(AgentStateRow).where(AgentStateRow.id == persona_id)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                return {
                    "stats": dict(row.stats or {}),
                    "inventory": list(row.inventory or []),
                    "room_id": row.room_id,
                }
        except Exception:
            logger.exception("Agent state load failed for %s", persona_id)
            return None

    async def _delete_row(self, persona_id: str) -> None:
        try:
            from sqlalchemy import delete

            from fablestar.state.models import AgentState as AgentStateRow

            async with self.server.db.session_factory() as db:
                async with db.begin():
                    await db.execute(delete(AgentStateRow).where(AgentStateRow.id == persona_id))
        except Exception:
            logger.exception("Agent state delete failed for %s", persona_id)

    async def flush_all(self) -> None:
        """Upsert every live agent's Redis state into agent_state (persistence cadence)."""
        if not self.agents:
            return
        try:
            from datetime import datetime

            from sqlalchemy import select

            from fablestar.state.models import AgentState as AgentStateRow

            async with self.server.db.session_factory() as db:
                async with db.begin():
                    for state in self.agents.values():
                        name = state.persona.name
                        room_id = await self.server.redis.get_player_location(name)
                        stats = await self.server.redis.get_player_stats(name)
                        inventory = await self.server.redis.get_player_inventory(name)
                        self._append_progress_sample(stats)
                        await self.server.redis.set_player_stats(name, stats)
                        result = await db.execute(
                            select(AgentStateRow).where(AgentStateRow.id == state.persona.id)
                        )
                        row = result.scalar_one_or_none()
                        if row is None:
                            row = AgentStateRow(id=state.persona.id, name=name)
                            db.add(row)
                        row.name = name
                        row.room_id = room_id or state.persona.spawn_room
                        row.stats = stats
                        row.inventory = list(inventory)
                        row.updated_at = datetime.utcnow()
        except Exception:
            logger.exception("Agent state flush failed")

    PROGRESS_KEY = "progress_log"
    PROGRESS_CAP = 400  # 60s cadence → ~6.5h of history in the stats blob

    def _append_progress_sample(self, stats: dict[str, Any]) -> None:
        """Time-series sample for the admin XP-progression chart (flush cadence)."""
        try:
            from fablestar.proficiencies.state_helpers import total_proficiency_levels

            counters = stats.get("counters") if isinstance(stats.get("counters"), dict) else {}
            try:
                levels = total_proficiency_levels(
                    stats, registry=self.server.content_loader.get_proficiency_registry()
                )
            except Exception:
                levels = 0
            log = stats.get(self.PROGRESS_KEY)
            if not isinstance(log, list):
                log = []
                stats[self.PROGRESS_KEY] = log
            log.append(
                {
                    "t": int(time.time()),
                    "levels": levels,
                    "kills": int(counters.get("kills", 0)),
                    "deaths": int(counters.get("deaths", 0)),
                    "goals": int(counters.get("goals_completed", 0)),
                    "rooms": len(stats.get("visited_rooms") or []),
                }
            )
            del log[: -self.PROGRESS_CAP]
        except Exception:
            logger.debug("progress sample skipped", exc_info=True)

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
        if not state.enabled:
            return
        name = state.persona.name
        room_id = await server.redis.get_player_location(name)
        if not room_id:
            return
        room = server.content_loader.get_room(room_id)
        if room is None:
            return
        stats = await server.redis.get_player_stats(name)

        # Death: wake in the medbay at half health, like a player relogging
        # at 0 hp — no immortal corpses wandering the halls.
        if int(stats.get("hp", 1)) <= 0:
            from fablestar.agents.feelings import remember
            from fablestar.effects.engine import clear_on_death

            clear_on_death(stats)
            stats["hp"] = max(1, int(stats.get("max_hp", 20)) // 2)
            remember(stats, "died and woke in the clinic, patched together")
            try:
                from fablestar.achievements.engine import record_counter

                record_counter(
                    stats, server.content_loader.get_achievement_registry(), "deaths"
                )
            except Exception:
                logger.debug("death counter skipped", exc_info=True)
            from fablestar.world.defaults import RESPAWN_ROOM

            respawn_room = RESPAWN_ROOM
            if server.content_loader.get_room(respawn_room) is None:
                respawn_room = state.persona.spawn_room
            await server.redis.set_player_stats(name, stats)
            await server.redis.set_player_location(name, respawn_room)
            state.goal_commands = []
            state.goal_label = None
            state.last_hp = stats["hp"]
            state.last_action = "respawn: clinic"
            state.last_action_at = time.time()
            state.pov.append(
                {
                    "at": time.time(),
                    "kind": "body",
                    "prompt": "[reflex] death",
                    "response": f"respawn {respawn_room}",
                }
            )
            del state.pov[:-20]
            logger.info("Agent %s died; respawned in %s", state.persona.id, respawn_room)
            return

        # Feelings: event detection + decay (deterministic, cheap).
        from fablestar.agents import feelings as fx

        hp_now = int(stats.get("hp", 1))
        if state.last_hp is not None and hp_now < state.last_hp:
            fx.on_hurt(
                stats, state.persona, (state.last_hp - hp_now) / max(1, stats.get("max_hp", 1))
            )
        state.last_hp = hp_now
        room_players = await server.redis.get_room_players(room_id)
        for other in room_players:
            if other != name:
                fx.on_company(stats, state.persona, other)
        fx.decay_tick(stats, state.persona)
        # Decay always mutates, so one unconditional write per tick.
        await server.redis.set_player_stats(name, stats)

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
        # Voice first: being spoken to outranks reflexes short of combat.
        if not ctx.hostiles:
            try:
                if await self.brain.maybe_voice(state):
                    return
            except Exception as exc:
                logger.warning("Agent voice failed for %s: %s", state.persona.id, exc)

        # Intent: idle, unhurt-enough, no goal, a real player present -> ask
        # the brain for a goal and compile it into a Body script.
        agent_names = {s.persona.name for s in self.agents.values()}
        players_present = [p for p in room_players if p != name and p not in agent_names]
        if not ctx.hostiles and not state.goal_commands and players_present:
            try:
                intent = await self.brain.maybe_intent(
                    state, players_present, self._known_rooms(state)
                )
                if intent:
                    await self._apply_intent(state, intent, room_id, stats)
            except Exception as exc:
                logger.warning("Agent intent failed for %s: %s", state.persona.id, exc)
            ctx.goal_commands = list(state.goal_commands)

        reason, command = decide(ctx, state.rng)
        if command is None:
            return
        if reason == "goal" and state.goal_commands:
            state.goal_commands.pop(0)
            if not state.goal_commands:
                from fablestar.agents import feelings as fx2

                fx2.on_goal_done(stats, state.persona)
                if state.goal_label:
                    fx2.remember(stats, f"finished: {state.goal_label}")
                try:
                    from fablestar.achievements.engine import record_counter

                    record_counter(
                        stats,
                        server.content_loader.get_achievement_registry(),
                        "goals_completed",
                    )
                except Exception:
                    logger.debug("goal counter skipped", exc_info=True)
                state.goal_label = None
                await server.redis.set_player_stats(name, stats)
        if reason == "wander":
            lo, hi = WANDER_COOLDOWN_S
            state.next_wander_at = now + state.rng.uniform(lo, hi)
        state.last_action = f"{reason}: {command}"
        state.last_action_at = now
        state.pov.append(
            {"at": now, "kind": "body", "prompt": f"[reflex] {reason}", "response": command}
        )
        del state.pov[:-20]
        await server.dispatcher.dispatch(state.session, command)

    # ------------------------------------------------------------------
    # Intent (M4) — compile brain goals into Body scripts
    # ------------------------------------------------------------------

    def _known_rooms(self, state: AgentState) -> list[str]:
        """Room slugs the agent can path to (its zone's walked exits map)."""
        zone = state.persona.spawn_zone()
        return sorted(r.split(":")[-1] for r in self._exits_map(zone))

    def _entity_room_finder(self, zone: str):
        """target substring -> a room_id whose spawns include a matching template."""

        def find(target: str) -> str | None:
            if not target:
                return None
            for room_id in self._exits_map(zone):
                room = self.server.content_loader.get_room(room_id)
                if room is None:
                    continue
                for spawn in getattr(room, "entity_spawns", []) or []:
                    template = getattr(spawn, "template", "")
                    tmpl = self.server.content_loader.get_entity_template(template)
                    hay = f"{template} {tmpl.name if tmpl else ''}".lower()
                    if target in hay:
                        return room_id
            return None

        return find

    async def _apply_intent(
        self, state: AgentState, intent: dict[str, str], room_id: str, stats: dict[str, Any]
    ) -> None:
        from fablestar.agents.brain import compile_goal
        from fablestar.agents.feelings import remember

        zone = state.persona.spawn_zone()
        compiled = compile_goal(
            intent, room_id, zone, self._exits_map(zone), self._entity_room_finder(zone)
        )
        why = intent.get("why") or "no reason given"
        if compiled is None:
            remember(stats, f"considered {intent['goal']} {intent['target']} but let it go")
        else:
            label, commands = compiled
            state.goal_label = label
            state.goal_commands = commands
            remember(stats, f"decided to {label} — {why}")
            logger.info("Agent %s intent: %s (%s)", state.persona.id, label, why)
        await self.server.redis.set_player_stats(state.persona.name, stats)

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
