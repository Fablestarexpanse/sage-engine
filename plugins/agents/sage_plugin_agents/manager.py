"""
AgentManager — spawns agent bodies and drives their reflex ticks.

Agents are full citizens of the session layer: attached as virtual sessions, present in room
sets, acting only via dispatched command strings. The Body (rules) acts every tick; the Brain
(LLM) runs in the background for voice, banter and intent. Everything world-specific — what food
is called, which rooms are social, where evenings are spent — comes from world params.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from pathlib import Path
from typing import Any

from sage.api import PluginAPI

from . import feelings as fx
from .body import WANDER_COOLDOWN_S, BodyContext, decide, hostiles_in, route_path, route_step
from .brain import AgentBrain, compile_goal
from .models import AgentPersonaModel
from .registry import AgentRegistry, load_agents
from .session import AgentSession
from .store import AgentStore

logger = logging.getLogger(__name__)

AGENT_TICK_SECONDS = 2.0  # body decisions every 2 s
INVENTORY_SOFT_CAP = 12  # go sell before the 14-item loot cap
CONTRACT_TRIP_LIMIT = 6  # hunting trips with zero progress before giving up
IDLE_INTENT_CHANCE = 0.02  # per tick, when no human is present (~1 plan per ~100s)
PROGRESS_KEY = "progress_log"
PROGRESS_CAP = 1600  # 60s cadence -> ~26h of history (overnight soak safe)


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
        # POV log for the admin "look through their eyes" panel.
        self.pov: list[dict[str, Any]] = []
        self.next_life_goal_at = 0.0  # throttle needs-driven goals (rent retries etc.)
        self.brain_task: asyncio.Task | None = None  # in-flight LLM pass
        self.rng = random.Random(hash(persona.id) & 0xFFFF)


class AgentManager:
    def __init__(self, api: PluginAPI):
        self.api = api
        self.agents: dict[str, AgentState] = {}  # persona.id -> state
        self._spawned = False
        self.store = AgentStore(api)
        self.brain = AgentBrain(api, self)
        self._personas = api.content.cached("agents", load_agents)
        self._exit_maps: dict[str, tuple[tuple, dict[str, dict[str, str]]]] = {}
        self._stamp: tuple = ()
        self._stamp_at = float("-inf")
        # World params: the life-goal vocabulary of this world.
        self.food_item: str = api.param("food_item", "")
        self.forage_item: str = api.param("forage_item", "")
        self.social_zones: set[str] = set(api.param("social_zones", []) or [])
        self.evening_room: str = api.param("evening_room", "")

    def registry(self) -> AgentRegistry:
        return self._personas.get()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def spawn_all(self) -> None:
        for persona in self.registry().all():
            if persona.enabled and persona.id not in self.agents:
                try:
                    await self.spawn(persona)
                except Exception as exc:
                    logger.error("Agent %s failed to spawn: %s", persona.id, exc)
        self._spawned = True

    async def spawn(self, persona: AgentPersonaModel) -> None:
        api = self.api
        session = AgentSession(persona.id, persona.name)
        api.sessions.attach(session)

        # Durable state wins over the persona seed (memories/feelings/gear
        # survive server restarts); admin restart deletes the row first.
        row = await self.store.load(persona.id)
        if row is not None:
            stats = dict(row["stats"])
            stats["is_agent"] = True
            inventory = list(row["inventory"])
            room_id = row["room_id"]
            if api.content.room(room_id) is None:
                room_id = persona.spawn_room
        else:
            stats = dict(persona.stats)
            stats.setdefault("max_hp", stats.get("hp", 60))
            stats.setdefault("hp", stats["max_hp"])
            stats["is_agent"] = True
            # Agents are computer-controlled players: the world's progression seeds their
            # attribute spread the way it does a new player's.
            api.progression.seed_attributes(stats, dict(persona.attributes))
            stats.setdefault("counters", {})
            if api.wallet.enabled:
                api.wallet.set(stats, int(persona.money))

            inventory: list[dict[str, Any]] = []
            # Equip persona gear (slot -> template id) through the equipment plugin, when enabled.
            equipment = self._service("equipment")
            for template_id in persona.gear.values() if equipment else ():
                template = api.content.item_template(template_id)
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
                _, inventory = equipment.equip(stats, [*inventory, item], item, template)
            room_id = persona.spawn_room

        await api.characters.place(persona.name, stats, inventory, room_id)
        self.agents[persona.id] = AgentState(persona, session)
        logger.info(
            "Agent spawned: %s (%s) in %s%s",
            persona.name,
            persona.id,
            room_id,
            " [restored]" if row is not None else "",
        )

    async def despawn(self, agent_id: str) -> None:
        state = self.agents.pop(agent_id, None)
        if state is None:
            return
        name = state.persona.name
        await self.api.characters.remove(name)
        self.api.sessions.detach(name)
        logger.info("Agent despawned: %s", name)

    async def restart(self, agent_id: str) -> None:
        """Reset: drop durable state and respawn fresh from the persona on disk."""
        await self.despawn(agent_id)
        await self.store.delete(agent_id)
        persona = self.registry().get(agent_id)
        if persona and persona.enabled:
            await self.spawn(persona)

    # ------------------------------------------------------------------
    # Durability (plg_agents_state; flushed on the persistence cadence)
    # ------------------------------------------------------------------

    async def flush_all(self) -> None:
        """Upsert every live agent's hot state into plg_agents_state."""
        rows = []
        for state in list(self.agents.values()):
            name = state.persona.name
            stats = await self.api.characters.stats(name)
            self._append_progress_sample(stats)
            await self.api.characters.save_stats(name, stats)
            rows.append(
                {
                    "id": state.persona.id,
                    "name": name,
                    "room_id": await self.api.state.location(name) or state.persona.spawn_room,
                    "stats": stats,
                    "inventory": list(await self.api.inventory.get(name)),
                }
            )
        await self.store.save(rows)

    def _append_progress_sample(self, stats: dict[str, Any]) -> None:
        """Time-series sample for the admin progression chart (flush cadence)."""
        try:
            counters = stats.get("counters") if isinstance(stats.get("counters"), dict) else {}
            log = stats.get(PROGRESS_KEY)
            if not isinstance(log, list):
                log = []
                stats[PROGRESS_KEY] = log
            log.append(
                {
                    "t": int(time.time()),
                    "levels": self.api.progression.total_levels(stats),
                    "kills": int(counters.get("kills", 0)),
                    "deaths": int(counters.get("deaths", 0)),
                    "goals": int(counters.get("goals_completed", 0)),
                    "rooms": len(stats.get("visited_rooms") or []),
                }
            )
            del log[:-PROGRESS_CAP]
        except Exception:
            logger.debug("progress sample skipped", exc_info=True)

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    async def on_tick(self, tick_count: int) -> None:
        if not self._spawned:
            await self.spawn_all()

        # Agents tick concurrently: a serial pass (8 agents x many Redis round-trips, plus
        # replies) overran the tick budget. Money between characters goes through the wallet's
        # atomic pending counter, so concurrent stats writes can't lose a keeper's takings.
        async def _one(agent_id: str) -> None:
            state = self.agents.get(agent_id)
            if state is None:
                return
            try:
                await self._tick_agent(state)
            except Exception as exc:
                logger.warning("Agent tick failed for %s: %s", agent_id, exc)

        await asyncio.gather(*(_one(a) for a in list(self.agents)))

    async def _tick_agent(self, state: AgentState) -> None:
        api = self.api
        if not state.enabled:
            return
        name = state.persona.name
        room_id = await api.state.location(name)
        if not room_id:
            return
        room = api.content.room(room_id)
        if room is None:
            return
        stats = await api.characters.stats(name)

        # Bank money other characters owe this agent (shop takings).
        try:
            if await api.wallet.bank_pending(name, stats):
                await api.characters.save_stats(name, stats)
        except Exception:
            logger.debug("pending wallet merge failed for %s", name, exc_info=True)

        if int(stats.get("hp", 1)) <= 0:
            await self._respawn(state, stats, room_id)
            return

        # Feelings: event detection + decay (deterministic, cheap).
        hp_now = int(stats.get("hp", 1))
        if state.last_hp is not None and hp_now < state.last_hp:
            fx.on_hurt(
                stats, state.persona, (state.last_hp - hp_now) / max(1, stats.get("max_hp", 1))
            )
        state.last_hp = hp_now
        room_players = await api.rooms.players(room_id)
        for other in room_players:
            if other != name:
                fx.on_company(stats, state.persona, other)
        fx.decay_tick(stats, state.persona)
        # Decay always mutates, so one unconditional write per tick.
        await api.characters.save_stats(name, stats)

        entity_states = await api.rooms.entities(room_id)

        def tags_of(template_id: str):
            template = api.content.entity_template(template_id)
            return template.tags if template else set()

        inventory = await api.inventory.get(name)
        consumables = []
        consumable_rules = self._service("consumables")
        for it in inventory if consumable_rules else ():
            template = api.content.item_template(it.get("template", ""))
            if template and consumable_rules.heal_of(template) > 0:
                consumables.append(it.get("name", template.name))

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
            for item in await api.rooms.items(room_id):
                if int(item.get("value", 0) or 0) > 0:
                    floor_valuables.append(item.get("name", ""))
                if len(floor_valuables) >= 3:
                    break

        now = time.time()
        shop = self._shop_at(room_id)
        ctx = BodyContext(
            hp=int(stats.get("hp", 1)),
            max_hp=int(stats.get("max_hp", 1)),
            room_type=room.type,
            exits=list(room.exits.keys()),
            hostiles=hostiles_in(entity_states, tags_of),
            consumables=consumables,
            resting=bool(api.effects.find(stats, "body.resting")),
            goal_commands=list(state.goal_commands),
            next_routine_direction=self._routine_direction(state, room_id),
            wander_ready=now >= state.next_wander_at,
            in_buying_shop=bool(shop is not None and shop.buys and shop.owner != name),
            sellable_count=sellable_count,
            floor_valuables=floor_valuables,
            hungry=float((stats.get("feelings", {}).get("needs", {}) or {}).get("hunger", 0.0))
            > 0.7,
        )
        # Deterministic life goals first (survival never waits on an LLM).
        if not ctx.hostiles and not state.goal_commands and time.time() >= state.next_life_goal_at:
            lodging_desk = (
                await self._lodging_choice(api.wallet.balance(stats))
                if not stats.get("home_room")
                else None
            )
            life = self._life_goal(state, stats, room_id, ctx, inventory, lodging_desk)
            if life is not None:
                state.next_life_goal_at = time.time() + 120.0
                state.goal_label, state.goal_commands = life
                fx.remember(stats, f"needed to {state.goal_label}")
                api.telemetry.event(
                    "life_goal",
                    agent=state.persona.id,
                    room=room_id,
                    goal=state.goal_label,
                    commands=len(state.goal_commands),
                )
                await api.characters.save_stats(name, stats)
                ctx.goal_commands = list(state.goal_commands)

        # The brain (voice, banter, intent) runs as a background task so a slow generation
        # never freezes this agent's slice of the tick. The Body keeps acting meanwhile.
        agent_names = {a.persona.name for a in self.agents.values()}
        brain_busy = state.brain_task is not None and not state.brain_task.done()
        if not ctx.hostiles and not brain_busy:
            players_present = [p for p in room_players if p != name and p not in agent_names]
            others = [p for p in room_players if p != name and p in agent_names]
            state.brain_task = asyncio.get_running_loop().create_task(
                self._think(
                    state,
                    room_id=room_id,
                    social_room=room_id.split(":")[0] in self.social_zones,
                    players_present=players_present,
                    banter_with=state.rng.choice(others)
                    if others and state.rng.random() < 0.08
                    else None,
                    # With nobody around, still plan now and then so the brain
                    # isn't idle all night.
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
                fx.on_goal_done(stats, state.persona)
                if state.goal_label:
                    fx.remember(stats, f"finished: {state.goal_label}")
                await api.counters.count(name, stats, "goals_completed")
                state.goal_label = None
                await api.characters.save_stats(name, stats)
        if reason == "wander":
            lo, hi = WANDER_COOLDOWN_S
            state.next_wander_at = now + state.rng.uniform(lo, hi)
        state.last_action = f"{reason}: {command}"
        state.last_action_at = now
        api.telemetry.event(
            "agent_action",
            agent=state.persona.id,
            room=room_id,
            reason=reason,
            command=command,
            hp=int(stats.get("hp", 0)),
            money=api.wallet.balance(stats),
        )
        await api.telemetry.heat("presence", room_id)
        await api.telemetry.heat(f"presence:{state.persona.id}", room_id)
        state.pov.append(
            {"at": now, "kind": "body", "prompt": f"[reflex] {reason}", "response": command}
        )
        del state.pov[:-20]
        await api.sessions.dispatch(state.session, command)

        # Post-action feelings: eating settles hunger; sleeping in your own
        # rented room beats any bench.
        if reason == "eat" or command == "rest":
            post_stats = await api.characters.stats(name)
            if reason == "eat":
                fx.on_ate(post_stats, state.persona)
            if command == "rest" and post_stats.get("home_room") == room_id:
                fx.on_slept_home(post_stats, state.persona)
            await api.characters.save_stats(name, post_stats)

    async def _respawn(self, state: AgentState, stats: dict[str, Any], room_id: str) -> None:
        """Death: wake where the world's respawn policy says, billed like a player."""
        api = self.api
        name = state.persona.name
        api.effects.clear_on_death(stats)
        plan = api.resolvers.get("death.respawn")(api.world, stats, api.wallet.balance(stats))
        stats["hp"] = plan.hp
        bill = api.wallet.take_up_to(stats, plan.bill) if api.wallet.enabled else 0
        currency = api.wallet.name() if api.wallet.enabled else ""
        fx.remember(
            stats,
            api.t("agents.memory.died_billed", bill=bill, currency=currency)
            if bill
            else api.t("agents.memory.died_free"),
        )
        await api.counters.count(name, stats, "deaths")
        respawn_room = plan.room_id if api.content.room(plan.room_id) else state.persona.spawn_room
        await api.characters.save_stats(name, stats)
        await api.characters.move(name, respawn_room)
        state.goal_commands = []
        state.goal_label = None
        state.last_hp = stats["hp"]
        state.last_action = "respawn"
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
        api.telemetry.event(
            "agent_death",
            agent=state.persona.id,
            room=room_id,
            respawn=respawn_room,
            bill=bill,
            money=api.wallet.balance(stats),
        )
        await api.telemetry.heat("deaths", room_id)
        logger.info("Agent %s died; respawned in %s", state.persona.id, respawn_room)

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
                    stats = await self.api.characters.stats(name)
                    here = await self.api.state.location(name) or room_id
                    await self._apply_intent(state, intent, here, stats)
        except Exception as exc:
            logger.warning("Agent brain pass failed for %s: %s", state.persona.id, exc)

    # ------------------------------------------------------------------
    # Other plugins' services (optional dependencies)
    # ------------------------------------------------------------------

    def _service(self, name: str) -> Any:
        try:
            return self.api.services.get(name)
        except Exception:
            return None

    def _shop_at(self, room_id: str | None) -> Any:
        shops = self._service("shop")
        return shops.at(room_id) if shops else None

    async def _lodging_choice(self, money: int) -> str | None:
        """Desk room with a free (or lapsed) bed this agent can afford, cheapest first."""
        lodgings = self._service("lodging")
        if lodgings is None:
            return None
        now = time.time()
        try:
            rentals = await lodgings.rentals()
        except Exception:
            return None
        options = []
        for zone in {s.persona.spawn_zone() for s in self.agents.values()}:
            for rid in self._exits_map(zone):
                lodging = lodgings.at(rid)
                if (
                    lodging
                    and money >= lodging.price + 10
                    and lodgings.free_rooms(lodging, rentals, now)
                ):
                    options.append((lodging.price, rid))
        return min(options)[1] if options else None

    # ------------------------------------------------------------------
    # Life goals
    # ------------------------------------------------------------------

    def _life_goal(
        self,
        state: AgentState,
        stats: dict[str, Any],
        room_id: str,
        ctx: BodyContext,
        inventory: list[dict[str, Any]],
        lodging_desk: str | None = None,
    ) -> tuple[str, list[str]] | None:
        """Deterministic needs-driven goals, most urgent first. (label, commands) or None."""
        factions = self._service("factions")
        zone = state.persona.spawn_zone()
        exits_of = self._exits_map(zone)
        needs = (stats.get("feelings", {}) or {}).get("needs", {}) or {}
        money = self.api.wallet.balance(stats)
        home = stats.get("home_room")
        hp_frac = int(stats.get("hp", 1)) / max(1, int(stats.get("max_hp", 1)))
        hunger = float(needs.get("hunger", 0))

        def go(label, target, then=()):
            path = route_path(room_id, target, exits_of)
            if path is None or (not path and not then):
                return None
            return (label, [*path, *then])

        # 1. Wounded: get somewhere safe and heal before anything else. Home if
        #    you have one, else the respawn room; the Body's rest reflex takes over
        #    in a safe room.
        if hp_frac < 0.5:
            current = self.api.content.room(room_id)
            if current is None or current.type != "safe":
                g = go("retreat to heal", home or self.api.world.respawn_room)
                if g:
                    return g

        # 2. Starving with nothing to eat: buy if you can, forage if you can't.
        if hunger > 0.85 and not ctx.consumables:
            if money >= 12 and self.food_item:
                seller = self._shop_finder(zone, buying=False)(self.food_item)
                if seller:
                    g = go("buy food (starving)", seller, [f"buy {self.food_item}"])
                    if g:
                        return g
            spot = self._search_room_finder(zone)(self.forage_item) if self.forage_item else None
            if spot:
                g = go("forage for food", spot, ["search", "search"])
                if g:
                    return g

        # 3. Pack nearly full of loot: go sell it.
        sellable = sum(1 for it in inventory if int(it.get("value", 0) or 0) > 0)
        if len(inventory) >= INVENTORY_SOFT_CAP and sellable:
            buyer = self._shop_finder(zone, buying=True, exclude_owner=state.persona.name)()
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
                    # Arriving is enough: the fight reflex and the kill event do the rest.
                    g = go(f"hunt {self._entity_name(target)}s (contract)", hunt_room)
                    if g:
                        mission["trips"] = trips + 1
                        return g
        elif float(needs.get("purpose", 0)) > 0.8 and hp_frac >= 0.7 and factions:
            hiring = [
                f
                for f in factions.registry().all()
                if f.offers_missions() and factions.will_deal(stats, f)
            ]
            if hiring:
                # Spread work across factions instead of the first one loaded.
                faction = state.rng.choice(hiring)
                return (f"take work: {faction.name}", [f"missions accept {faction.id}"])

        # 5. Homeless, with savings, and a bed actually free somewhere.
        if not home and lodging_desk:
            g = go("rent a room", lodging_desk, ["rent"])
            if g:
                return g

        # 6. Lease nearly up and can pay: renew at the desk that let the room.
        home_until = float(stats.get("home_until", 0) or 0)
        if home and 0 < home_until - time.time() < 10 * 60 and money >= 25:
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

        # 8. Evening: the warm-hearted drift toward the world's evening room now and then.
        if (
            self.evening_room
            and self.api.clock.phase() == "evening"
            and state.persona.temperament.warmth > 0.5
            and room_id.split(":")[0] != self.evening_room.split(":")[0]
            and state.rng.random() < 0.04
        ):
            room = self.api.content.room(self.evening_room)
            g = go(
                f"spend the evening at {room.name if room else self.evening_room}",
                self.evening_room,
            )
            if g:
                return g
        return None

    def _entity_name(self, template_id: str) -> str:
        template = self.api.content.entity_template(template_id)
        return template.name if template else template_id.replace("_", " ")

    def _item_name(self, template_id: str) -> str:
        template = self.api.content.item_template(template_id)
        return template.name if template else template_id.replace("_", " ")

    def _desk_for(self, zone: str, rented_room: str) -> str | None:
        lodgings = self._service("lodging")
        return lodgings.desk_for(list(self._exits_map(zone)), rented_room) if lodgings else None

    def _search_room_finder(self, zone: str):
        """item template -> a room whose search profiles can yield it."""

        def find(template_id: str) -> str | None:
            searches = self._service("search")
            if searches is None:
                return None
            return searches.room_yielding(list(self._exits_map(zone)), template_id)

        return find

    def _shop_finder(self, zone: str, *, buying: bool, exclude_owner: str = ""):
        """buying=True: () -> the best-paying room whose shop buys (never the agent's own till).
        buying=False: (item substring) -> the cheapest room selling a match. Comparison-shopping,
        not first-found, so one shop doesn't take every sale."""

        def find_buyer() -> str | None:
            best = None
            for room_id in self._exits_map(zone):
                shop = self._shop_at(room_id)
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
                shop = self._shop_at(room_id)
                if shop is None:
                    continue
                for entry in shop.sells:
                    template = self.api.content.item_template(entry.template)
                    hay = f"{entry.template} {template.name if template else ''}".lower()
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
                room = self.api.content.room(room_id)
                if room is None:
                    continue
                for spawn in getattr(room, "entity_spawns", []) or []:
                    template_id = getattr(spawn, "template", "")
                    template = self.api.content.entity_template(template_id)
                    hay = f"{template_id} {template.name if template else ''}".lower()
                    if target in hay:
                        return room_id
            return None

        return find

    # ------------------------------------------------------------------
    # Intent — compile brain goals into Body scripts
    # ------------------------------------------------------------------

    def _known_rooms(self, state: AgentState) -> list[str]:
        """Room slugs the agent can path to (its zone's walked exits map)."""
        return sorted(r.split(":")[-1] for r in self._exits_map(state.persona.spawn_zone()))

    async def _apply_intent(
        self, state: AgentState, intent: dict[str, str], room_id: str, stats: dict[str, Any]
    ) -> None:
        zone = state.persona.spawn_zone()
        compiled = compile_goal(
            intent,
            room_id,
            zone,
            self._exits_map(zone),
            self._entity_room_finder(zone),
            buyer_room_finder=self._shop_finder(zone, buying=True),
            seller_room_finder=self._shop_finder(zone, buying=False),
            default_buy=self.food_item,
        )
        why = intent.get("why") or "no reason given"
        if compiled is None:
            fx.remember(stats, f"considered {intent['goal']} {intent['target']} but let it go")
            # Parsed but unrealizable (e.g. hunt -> a room): a brain-quality metric.
            self.api.telemetry.event(
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
            fx.remember(stats, f"decided to {label} — {why}")
            logger.info("Agent %s intent: %s (%s)", state.persona.id, label, why)
            self.api.telemetry.event(
                "intent", agent=state.persona.id, room=room_id, goal=label, why=why
            )
        await self.api.characters.save_stats(state.persona.name, stats)

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
        """room_id -> {direction: destination} for a zone, walked from every agent anchor in it.

        Rebuilt when any zone's room files change, so edited maps apply without a restart.
        """
        stamp = self._rooms_stamp()
        cached = self._exit_maps.get(zone)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        exits_of: dict[str, dict[str, str]] = {}
        seeds = [p.spawn_room for p in self.registry().all() if p.spawn_zone() == zone]
        queue = list(dict.fromkeys(seeds))
        seen = set(queue)
        while queue:
            room_id = queue.pop()
            room = self.api.content.room(room_id)
            if room is None:
                continue
            exits_of[room_id] = {d: ex.destination for d, ex in room.exits.items()}
            for dest in exits_of[room_id].values():
                if dest not in seen:
                    seen.add(dest)
                    queue.append(dest)
        self._exit_maps[zone] = (stamp, exits_of)
        return exits_of

    def _rooms_stamp(self) -> tuple:
        """Room files' mtimes, rescanned at most every few seconds (maps are read every tick)."""
        now = time.monotonic()
        if now - self._stamp_at >= 5.0:
            zones = Path(self.api.world.content_dir) / "world" / "zones"
            files = sorted(zones.glob("*/rooms/*.yaml")) if zones.is_dir() else []
            self._stamp = tuple((str(f), f.stat().st_mtime_ns) for f in files)
            self._stamp_at = now
        return self._stamp
