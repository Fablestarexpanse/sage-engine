"""
AgentManager — spawns agent bodies and drives their reflex ticks.

Agents are full citizens of the session layer: registered in SessionManager,
present in Redis room sets, acting only via dispatcher-dispatched command
strings. M1 scope: spawn from personas, wander routines, fight/flee/eat/rest
reflexes. Brains (LLM) arrive in M3/M4; restart/give/teleport admin hooks
land in M2 but the manager API for them lives here from the start.
"""

import asyncio
import logging
import random
import time
import uuid
from typing import TYPE_CHECKING, Any

from sage.agents.body import (
    WANDER_COOLDOWN_S,
    BodyContext,
    decide,
    hostiles_in,
    route_step,
)
from sage.agents.models import AgentPersonaModel
from sage.agents.session import AgentSession

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)

AGENT_TICK_INTERVAL = 8  # 4 Hz tick → body decisions every 2 s (staggered)
CLINIC_BILL_DIGI = 10  # respawn cost, deducted down to zero (matches player bill)
LEASE_SWEEP_INTERVAL = 240  # ~60s: lapse expired rent leases
INVENTORY_SOFT_CAP = 12  # go sell before the 14-item loot cap
CONTRACT_TRIP_LIMIT = 6  # hunting trips with zero progress before giving up
IDLE_INTENT_CHANCE = 0.02  # per tick, when no human is present (~1 plan per ~100s)


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
        self.next_life_goal_at = 0.0  # throttle needs-driven goals (rent retries etc.)
        self.brain_task: asyncio.Task | None = None  # in-flight LLM pass
        self.rng = random.Random(hash(persona.id) & 0xFFFF)


class AgentManager:
    def __init__(self, server: "SageServer"):
        self.server = server
        self.agents: dict[str, AgentState] = {}  # persona.id -> state
        self._spawned = False
        self._brain = None  # lazy: config not fully loaded at construction

    @property
    def brain(self):
        if self._brain is None:
            from sage.agents.brain import AgentBrain

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
            from sage.proficiencies.state_helpers import ensure_proficiency_block

            ensure_proficiency_block(stats)
            if persona.attributes:
                attrs = stats["conduit"]["conduit_attributes"]
                for key, value in persona.attributes.items():
                    if key in attrs:
                        attrs[key] = int(value)
            stats.setdefault("counters", {})
            stats.setdefault("digi", int(persona.digi))

            inventory = []
            # Equip persona gear (slot -> template id) through the equipment engine.
            from sage.items.equipment import equip_item

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

            from sage.state.models import AgentState as AgentStateRow

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

            from sage.state.models import AgentState as AgentStateRow

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

            from sage.state.models import AgentState as AgentStateRow

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
    PROGRESS_CAP = 1600  # 60s cadence → ~26h of history (overnight soak safe)

    def _append_progress_sample(self, stats: dict[str, Any]) -> None:
        """Time-series sample for the admin XP-progression chart (flush cadence)."""
        try:
            from sage.proficiencies.state_helpers import total_proficiency_levels

            counters = stats.get("counters") if isinstance(stats.get("counters"), dict) else {}
            try:
                levels = total_proficiency_levels(stats)
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
        if tick_count % LEASE_SWEEP_INTERVAL == 0:
            try:
                from sage.commands.rent import expire_leases

                await expire_leases(self.server.redis)
            except Exception:
                logger.debug("lease sweep failed", exc_info=True)
        if tick_count % AGENT_TICK_INTERVAL != 0:
            return

        # Agents tick concurrently: the serial pass (8 agents x many Redis
        # round-trips, plus inline LLM replies) overran the 0.25s tick budget
        # on every agent tick overnight. Cross-agent money moves go through
        # the atomic pending-digi counter, so concurrent stats writes can't
        # lose a shopkeeper's takings.
        async def _one(agent_id: str):
            state = self.agents.get(agent_id)
            if state is None:
                return
            try:
                await self._tick_agent(state)
            except Exception as exc:
                logger.warning("Agent tick failed for %s: %s", agent_id, exc)

        await asyncio.gather(*(_one(a) for a in list(self.agents)))

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

        # Bank money other sessions owe this agent (shop takings). Written to an
        # atomic counter by the payer so concurrent ticks can't overwrite it.
        try:
            pending = await server.redis.client.getdel(f"digi_pending:{name}")
            if pending:
                stats["digi"] = max(0, int(stats.get("digi", 0) or 0) + int(pending))
                await server.redis.set_player_stats(name, stats)
        except Exception:
            logger.debug("pending digi merge failed for %s", name, exc_info=True)

        # Death: wake in the medbay at half health, like a player relogging
        # at 0 hp — no immortal corpses wandering the halls.
        if int(stats.get("hp", 1)) <= 0:
            from sage.agents.feelings import remember
            from sage.effects.engine import clear_on_death

            clear_on_death(stats)
            stats["hp"] = max(1, int(stats.get("max_hp", 20)) // 2)
            # The clinic doesn't work for free: dying costs Digi (down to 0).
            bill = min(int(stats.get("digi", 0) or 0), CLINIC_BILL_DIGI)
            stats["digi"] = int(stats.get("digi", 0) or 0) - bill
            remember(
                stats,
                f"died and woke in the clinic, patched together ({bill} Digi bill)"
                if bill
                else "died and woke in the clinic; too broke to bill",
            )
            from sage.world.counters import count

            await count(server, name, stats, "deaths")
            respawn_room = server.world.respawn_room
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
            from sage.telemetry import heat, log_event

            log_event(
                "agent_death",
                agent=state.persona.id,
                room=room_id,
                respawn=respawn_room,
                bill=bill,
                digi=int(stats.get("digi", 0) or 0),
            )
            await heat(server.redis, "deaths", room_id)
            logger.info("Agent %s died; respawned in %s", state.persona.id, respawn_room)
            return

        # Feelings: event detection + decay (deterministic, cheap).
        from sage.agents import feelings as fx

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

        from sage.effects.engine import find_effects

        equipped_ids = {
            (it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it
        }
        sellable_count = sum(
            1
            for it in inventory
            if it.get("id") not in equipped_ids and int(it.get("value", 0) or 0) > 0
        )

        # Valuable drops on the floor (looted when safe; capped so an agent
        # doesn't become a walking warehouse).
        floor_valuables: list[str] = []
        if len(inventory) < 14:
            for iid in await server.redis.get_room_items(room_id):
                iid = iid.decode() if isinstance(iid, bytes) else iid
                istate = await server.redis.get_item_state(iid)
                if istate and int(istate.get("value", 0) or 0) > 0:
                    floor_valuables.append(istate.get("name", ""))
                if len(floor_valuables) >= 3:
                    break

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
            in_buying_shop=bool(
                room.shop is not None and room.shop.buys and room.shop.owner != state.persona.id
            ),
            sellable_count=sellable_count,
            floor_valuables=floor_valuables,
            hungry=float((stats.get("feelings", {}).get("needs", {}) or {}).get("hunger", 0.0))
            > 0.7,
        )
        # Deterministic life goals first (survival never waits on an LLM):
        # starving -> buy food; homeless + flush -> rent a room; exhausted
        # with a home -> go sleep in it; evenings pull the warm toward the pub.
        if not ctx.hostiles and not state.goal_commands and time.time() >= state.next_life_goal_at:
            lodging_desk = (
                await self._lodging_choice(int(stats.get("digi", 0) or 0))
                if not stats.get("home_room")
                else None
            )
            life = self._life_goal(state, stats, room_id, ctx, inventory, lodging_desk)
            if life is not None:
                state.next_life_goal_at = time.time() + 120.0
                state.goal_label, state.goal_commands = life
                from sage.agents.feelings import remember

                remember(stats, f"needed to {state.goal_label}")
                from sage.telemetry import log_event

                log_event(
                    "life_goal",
                    agent=state.persona.id,
                    room=room_id,
                    goal=state.goal_label,
                    commands=len(state.goal_commands),
                )
                await server.redis.set_player_stats(name, stats)
                ctx.goal_commands = list(state.goal_commands)

        # The brain (voice, pub banter, intent) runs as a background task: the
        # LLM used to be awaited inline, freezing this agent's slice of the
        # tick for the whole generation. The Body keeps acting meanwhile.
        agent_names = {a.persona.name for a in self.agents.values()}
        brain_busy = state.brain_task is not None and not state.brain_task.done()
        if not ctx.hostiles and not brain_busy:
            players_present = [p for p in room_players if p != name and p not in agent_names]
            others = [p for p in room_players if p != name and p in agent_names]
            state.brain_task = asyncio.get_running_loop().create_task(
                self._think(
                    state,
                    room_id=room_id,
                    social_room=room_id.startswith("aipub:"),
                    players_present=players_present,
                    banter_with=state.rng.choice(others)
                    if others and state.rng.random() < 0.08
                    else None,
                    # With nobody around, still plan now and then so the brain
                    # isn't idle all night (0 intents in the first soak).
                    want_intent=not state.goal_commands
                    and (bool(players_present) or state.rng.random() < IDLE_INTENT_CHANCE),
                )
            )

        reason, command = decide(ctx, state.rng)
        if command is None:
            return
        if reason == "goal" and state.goal_commands:
            state.goal_commands.pop(0)
            if not state.goal_commands:
                from sage.agents import feelings as fx2

                fx2.on_goal_done(stats, state.persona)
                if state.goal_label:
                    fx2.remember(stats, f"finished: {state.goal_label}")
                from sage.world.counters import count

                await count(server, name, stats, "goals_completed")
                state.goal_label = None
                await server.redis.set_player_stats(name, stats)
        if reason == "wander":
            lo, hi = WANDER_COOLDOWN_S
            state.next_wander_at = now + state.rng.uniform(lo, hi)
        state.last_action = f"{reason}: {command}"
        state.last_action_at = now
        from sage.telemetry import heat, log_event

        log_event(
            "agent_action",
            agent=state.persona.id,
            room=room_id,
            reason=reason,
            command=command,
            hp=int(stats.get("hp", 0)),
            digi=int(stats.get("digi", 0) or 0),
        )
        await heat(server.redis, "presence", room_id)
        await heat(server.redis, f"presence:{state.persona.id}", room_id)
        state.pov.append(
            {"at": now, "kind": "body", "prompt": f"[reflex] {reason}", "response": command}
        )
        del state.pov[:-20]
        await server.dispatcher.dispatch(state.session, command)

        # Post-action feelings: eating settles hunger; sleeping in your own
        # rented room beats any bench.
        if reason == "eat" or command == "rest":
            from sage.agents import feelings as fx3

            post_stats = await server.redis.get_player_stats(name)
            if reason == "eat":
                fx3.on_ate(post_stats, state.persona)
            if command == "rest" and post_stats.get("home_room") == room_id:
                fx3.on_slept_home(post_stats, state.persona)
            await server.redis.set_player_stats(name, post_stats)

    async def _think(
        self,
        state: AgentState,
        *,
        room_id: str,
        social_room: bool,
        players_present: list[str],
        banter_with: str | None,
        want_intent: bool,
    ) -> None:
        """One background brain pass: reply if spoken to, else maybe banter,
        else maybe plan. Never raises into the event loop."""
        try:
            if await self.brain.maybe_voice(state, social_ok=social_room):
                return
            if social_room and banter_with and await self.brain.maybe_banter(state, banter_with):
                return
            if want_intent:
                intent = await self.brain.maybe_intent(
                    state, players_present, self._known_rooms(state)
                )
                if intent and not state.goal_commands:
                    name = state.persona.name
                    stats = await self.server.redis.get_player_stats(name)
                    here = await self.server.redis.get_player_location(name) or room_id
                    await self._apply_intent(state, intent, here, stats)
        except Exception as exc:
            logger.warning("Agent brain pass failed for %s: %s", state.persona.id, exc)

    # ------------------------------------------------------------------
    # Intent (M4) — compile brain goals into Body scripts
    # ------------------------------------------------------------------

    def _known_rooms(self, state: AgentState) -> list[str]:
        """Room slugs the agent can path to (its zone's walked exits map)."""
        zone = state.persona.spawn_zone()
        return sorted(r.split(":")[-1] for r in self._exits_map(zone))

    def _factions(self):
        """The factions plugin's service, or None when the world doesn't enable it.

        Transitional: engine code reads a plugin service by name until agents are a plugin
        themselves (phase-3 plan 3.8) and declare the dependency.
        """
        entry = getattr(getattr(self.server, "plugins", None), "services", {}).get("factions")
        return entry[1] if entry else None

    async def _lodging_choice(self, digi: int) -> str | None:
        """Desk room with a free (or lapsed) bed this agent can afford, cheapest first."""
        from sage.commands.rent import free_rooms, read_rentals

        now = time.time()
        try:
            rentals = await read_rentals(self.server.redis)
        except Exception:
            return None
        options = []
        for zone in {s.persona.spawn_zone() for s in self.agents.values()}:
            for rid in self._exits_map(zone):
                room = self.server.content_loader.get_room(rid)
                lodging = room.lodging if room else None
                if lodging and digi >= lodging.price + 10 and free_rooms(lodging, rentals, now):
                    options.append((lodging.price, rid))
        return min(options)[1] if options else None

    def _life_goal(
        self,
        state: AgentState,
        stats: dict[str, Any],
        room_id: str,
        ctx,
        inventory,
        lodging_desk: str | None = None,
    ):
        """Deterministic needs-driven goals, most urgent first. (label, commands) or None."""
        from sage.agents.body import route_path
        from sage.world.clock import day_phase

        factions = self._factions()

        zone = state.persona.spawn_zone()
        exits_of = self._exits_map(zone)
        needs = (stats.get("feelings", {}) or {}).get("needs", {}) or {}
        digi = int(stats.get("digi", 0) or 0)
        home = stats.get("home_room")
        hp_frac = int(stats.get("hp", 1)) / max(1, int(stats.get("max_hp", 1)))
        hunger = float(needs.get("hunger", 0))

        def go(label, target, then=()):
            path = route_path(room_id, target, exits_of)
            if path is None or (not path and not then):
                return None
            return (label, [*path, *then])

        # 1. Wounded: get somewhere safe and heal before anything else. Home if
        #    you have one, else the clinic; the Body's rest reflex takes over in
        #    a safe room. (Overnight Cutter fought, fled, and walked straight
        #    back in: 25 deaths.)
        if hp_frac < 0.5:
            current = self.server.content_loader.get_room(room_id)
            if current is None or current.type != "safe":
                g = go("retreat to heal", home or self.server.world.respawn_room)
                if g:
                    return g

        # 2. Starving with nothing to eat: buy if you can, forage if you can't.
        #    (Old Pell sat at hunger 1.0 all night with 6 Digi.)
        if hunger > 0.85 and not ctx.consumables:
            if digi >= 12:
                seller = self._shop_finder(zone, buying=False)("ration")
                if seller:
                    g = go("buy food (starving)", seller, ["buy ration"])
                    if g:
                        return g
            spot = self._search_room_finder(zone)("ration_pack")
            if spot:
                g = go("forage for food", spot, ["search", "search"])
                if g:
                    return g

        # 3. Pack nearly full of loot: go sell it (7 of 8 agents sat at the cap).
        sellable = sum(1 for it in inventory if int(it.get("value", 0) or 0) > 0)
        if len(inventory) >= INVENTORY_SOFT_CAP and sellable:
            buyer = self._shop_finder(zone, buying=True, exclude_owner=state.persona.id)()
            if buyer:
                g = go("sell a full pack", buyer, ["sell all"])
                if g:
                    return g

        # 4. Work: progress the contract, give up on hopeless ones, or take new
        #    work when purpose bites. Only healthy agents go hunting.
        mission = factions.active_mission(stats) if factions else None
        if mission:
            target = str(mission.get("target", ""))
            trips = int(mission.get("trips", 0))
            progress = int(mission.get("progress", 0))
            if trips >= CONTRACT_TRIP_LIMIT and progress * 2 < int(mission.get("count", 1)):
                return ("abandon a hopeless contract", ["missions abandon"])
            if mission.get("kind") == "collect":
                have = sum(1 for it in inventory if it.get("template") == target)
                if have >= int(mission.get("count", 0)):
                    return (f"deliver {self._item_name(target)}", ["missions complete"])
                spot = self._search_room_finder(zone)(target)
                if spot:
                    g = go(f"gather {self._item_name(target)}", spot, ["search"])
                    if g:
                        mission["trips"] = trips + 1
                        return g
            elif mission.get("kind") == "kill" and hp_frac >= 0.7:
                hunt_room = self._entity_room_finder(zone)(target.lower())
                if hunt_room and hunt_room != room_id:
                    # Arriving is enough: the fight reflex and the combat
                    # mission hook do the rest.
                    g = go(f"hunt {self._entity_name(target)}s (contract)", hunt_room)
                    if g:
                        mission["trips"] = trips + 1
                        return g
        elif float(needs.get("purpose", 0)) > 0.8 and hp_frac >= 0.7:
            hiring = (
                [
                    f
                    for f in factions.registry().all()
                    if f.offers_missions() and factions.will_deal(stats, f)
                ]
                if factions
                else []
            )
            if hiring:
                # Spread work across factions; overnight every contract went to
                # whichever faction happened to load first.
                faction = state.rng.choice(hiring)
                return (f"take work: {faction.name}", [f"missions accept {faction.id}"])

        # 5. Homeless, with savings, and a bed actually free somewhere.
        if not home and lodging_desk:
            g = go("rent a room", lodging_desk, ["rent"])
            if g:
                return g

        # 6. Lease nearly up and can pay: renew at the desk that let the room.
        home_until = float(stats.get("home_until", 0) or 0)
        if home and 0 < home_until - time.time() < 10 * 60 and digi >= 25:
            desk = self._desk_for(zone, home)
            if desk:
                g = go("renew my lease", desk, ["rent"])
                if g:
                    return g

        # 7. Exhausted with a home: sleep in your own bed.
        if home and float(needs.get("rest", 0)) > 0.95 and room_id != home:
            g = go("sleep at home", home, ["rest"])
            if g:
                return g

        # 8. Evening: the warm-hearted drift toward the pub now and then.
        if (
            day_phase() == "evening"
            and state.persona.temperament.warmth > 0.5
            and not room_id.startswith("aipub:")
            and state.rng.random() < 0.04
        ):
            g = go("evening at the AIpub", "aipub:main_bar")
            if g:
                return g
        return None

    def _entity_name(self, template_id: str) -> str:
        tmpl = self.server.content_loader.get_entity_template(template_id)
        return tmpl.name if tmpl else template_id.replace("_", " ")

    def _item_name(self, template_id: str) -> str:
        tmpl = self.server.content_loader.get_item_template(template_id)
        return tmpl.name if tmpl else template_id.replace("_", " ")

    def _desk_for(self, zone: str, rented_room: str) -> str | None:
        for rid in self._exits_map(zone):
            room = self.server.content_loader.get_room(rid)
            if room and room.lodging and rented_room in room.lodging.rooms:
                return rid
        return None

    def _search_room_finder(self, zone: str):
        """item template -> a room whose search profiles can yield it."""

        def find(template_id: str) -> str | None:
            for room_id in self._exits_map(zone):
                room = self.server.content_loader.get_room(room_id)
                if room is None:
                    continue
                for feature in room.features:
                    if feature.search and template_id in feature.search.items:
                        return room_id
            return None

        return find

    def _shop_finder(self, zone: str, *, buying: bool, exclude_owner: str = ""):
        """buying=True: () -> the best-paying room whose shop buys (never the
        agent's own till). buying=False: (item substring) -> the cheapest room
        selling a match. Comparison-shopping, not first-found: overnight the
        first-found AIpub took every food sale and Meri's store sold nothing."""

        def find_buyer() -> str | None:
            best = None
            for room_id in self._exits_map(zone):
                room = self.server.content_loader.get_room(room_id)
                shop = room.shop if room else None
                if shop is None or not shop.buys:
                    continue
                if exclude_owner and shop.owner == exclude_owner:
                    continue
                if best is None or shop.buy_rate > best[0]:
                    best = (shop.buy_rate, room_id)
            return best[1] if best else None

        def find_seller(item: str) -> str | None:
            item = (item or "").lower()
            best = None
            for room_id in self._exits_map(zone):
                room = self.server.content_loader.get_room(room_id)
                if room is None or room.shop is None:
                    continue
                for entry in room.shop.sells:
                    tmpl = self.server.content_loader.get_item_template(entry.template)
                    hay = f"{entry.template} {tmpl.name if tmpl else ''}".lower()
                    if item in hay and (best is None or entry.price < best[0]):
                        best = (entry.price, room_id)
            return best[1] if best else None

        return find_buyer if buying else find_seller

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
        from sage.agents.brain import compile_goal
        from sage.agents.feelings import remember

        zone = state.persona.spawn_zone()
        compiled = compile_goal(
            intent,
            room_id,
            zone,
            self._exits_map(zone),
            self._entity_room_finder(zone),
            buyer_room_finder=self._shop_finder(zone, buying=True),
            seller_room_finder=self._shop_finder(zone, buying=False),
        )
        why = intent.get("why") or "no reason given"
        if compiled is None:
            remember(stats, f"considered {intent['goal']} {intent['target']} but let it go")
            from sage.telemetry import log_event

            # Parsed but unrealizable (e.g. hunt -> a room): a brain-quality metric.
            log_event(
                "intent_rejected",
                agent=state.persona.id,
                room=room_id,
                goal=intent["goal"],
                target=intent["target"],
            )
        else:
            label, commands = compiled
            state.goal_label = label
            state.goal_commands = commands
            remember(stats, f"decided to {label} — {why}")
            logger.info("Agent %s intent: %s (%s)", state.persona.id, label, why)
            from sage.telemetry import log_event

            log_event("intent", agent=state.persona.id, room=room_id, goal=label, why=why)
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
