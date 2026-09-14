"""PluginAPI: the scoped surface a plugin's ``setup(api)`` receives (contracts C.4, C.5).

Every registration is tagged with the plugin id and recorded so the loader can seal the plugin
against its manifest and withdraw everything if setup fails or the plugin is torn down.
"""

from __future__ import annotations

import contextlib
import copy
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from sage import lexicon
from sage.plugins.manifest import PluginError


class _Commands:
    def __init__(self, api: PluginAPI):
        self._api = api

    def register(
        self, verb: str, handler: Callable[..., Any], aliases: list[str] | tuple[str, ...] = ()
    ) -> None:
        host = self._api._host
        for name in (verb, *aliases):
            if host.registry.get(name) is not None:
                raise PluginError(
                    f"plugin {self._api.id}: command or alias {name!r} already exists"
                )
        host.registry.register(verb, handler, list(aliases))
        self._api._record.record("commands", verb)
        self._api._cleanup.append(lambda: host.registry.unregister(verb))


class _Events:
    def __init__(self, api: PluginAPI):
        self._api = api

    def subscribe(self, event_type: type, handler: Callable[[Any], Any]) -> None:
        self._api._host.events.subscribe(event_type, handler, owner=self._api.id)
        self._api._record.record("events_subscribe", event_type.__name__)

    async def publish(self, event: Any) -> None:
        name = type(event).__name__
        if name not in self._api._record.manifest.touches.events_publish:
            raise PluginError(f"plugin {self._api.id} publishes undeclared event {name}")
        await self._api._host.events.publish(event)


class _Resolvers:
    def __init__(self, api: PluginAPI):
        self._api = api

    def define(self, slot: str, default: Callable[..., Any]) -> None:
        self._api._host.resolvers.define(slot, default, owner=self._api.id)
        self._api._record.record("resolvers_define", slot)
        self._api._cleanup.append(lambda: self._api._host.resolvers.withdraw(self._api.id))

    def provide(self, slot: str, fn: Callable[..., Any]) -> None:
        self._api._host.resolvers.provide(slot, fn, owner=self._api.id)
        self._api._record.record("resolvers", slot)
        self._api._cleanup.append(lambda: self._api._host.resolvers.withdraw(self._api.id))

    def get(self, slot: str) -> Callable[..., Any]:
        return self._api._host.resolvers.get(slot)


class _Tick:
    def __init__(self, api: PluginAPI):
        self._api = api

    def every(self, seconds: float, job: Callable[[int], Any], name: str) -> None:
        tick = self._api._host.tick_manager
        wrapper = tick.every(seconds, job, name=f"{self._api.id}.{name}")
        self._api._record.record("tick_jobs", name)
        self._api._cleanup.append(lambda: tick.unregister(wrapper))


def _engine_service_keys(world: Any) -> set[str]:
    """Stats keys engine services write on a plugin's behalf (wallet, counters)."""
    from sage.effects.engine import EFFECTS_KEY
    from sage.world.counters import COUNTERS_KEY, VISITED_KEY

    currencies = (c.key for c in getattr(world, "currencies", []) or [])
    return {COUNTERS_KEY, VISITED_KEY, EFFECTS_KEY, *currencies}


class _State:
    """Named per-character state blocks stored under the block name in the stats blob."""

    def __init__(self, api: PluginAPI):
        self._api = api
        self._defaults: dict[str, Callable[[], Any]] = {}

    def block(self, name: str, default: Callable[[], Any] = dict) -> None:
        owner = self._api._host.state_owners.setdefault(name, self._api.id)
        if owner != self._api.id:
            raise PluginError(f"plugin {self._api.id}: state block {name!r} belongs to {owner}")
        self._defaults[name] = default
        self._api._record.record("state_blocks", name)

    def _check(self, name: str) -> None:
        if name not in self._defaults:
            raise PluginError(
                f"plugin {self._api.id} uses state block {name!r} it did not register"
            )

    async def snapshot(self, player_id: str) -> dict[str, Any]:
        """A read-only copy of the character's whole stats blob (engine counters included)."""
        return copy.deepcopy(await self._api._host.redis.get_player_stats(player_id))

    @contextlib.asynccontextmanager
    async def edit(self, player_id: str) -> AsyncIterator[dict[str, Any]]:
        """Load the whole stats blob, let the plugin change it, save it on success.

        For work that spans the plugin's own blocks and engine services (wallet balances,
        counters — whose subscribers may update their own blocks). Changing any other top-level
        key (vitals, a world's progression data) raises PluginError and saves nothing.
        """
        redis = self._api._host.redis
        before = await redis.get_player_stats(player_id)
        stats = copy.deepcopy(before)
        yield stats
        allowed = (
            set(self._defaults)
            | set(self._api._host.state_owners)
            | _engine_service_keys(self._api._host.world)
            | set(self._api._record.manifest.touches.stats_keys)
        )
        changed = {k for k in set(before) | set(stats) if before.get(k) != stats.get(k)}
        stray = sorted(changed - allowed)
        if stray:
            raise PluginError(f"plugin {self._api.id} changed stats it does not own: {stray}")
        await redis.set_player_stats(player_id, stats)

    async def location(self, player_id: str) -> str | None:
        """The room a character is in (None when not in the world)."""
        return await self._api._host.redis.get_player_location(player_id)

    async def relocate(self, player_id: str, room_id: str) -> None:
        """Move a character to a room (room occupancy follows)."""
        await self._api._host.redis.set_player_location(player_id, room_id)

    async def get(self, player_id: str, name: str) -> Any:
        self._check(name)
        stats = await self._api._host.redis.get_player_stats(player_id)
        return stats.get(name, self._defaults[name]())

    async def set(self, player_id: str, name: str, value: Any) -> None:
        self._check(name)
        redis = self._api._host.redis
        stats = await redis.get_player_stats(player_id)
        stats[name] = value
        await redis.set_player_stats(player_id, stats)


class _Services:
    def __init__(self, api: PluginAPI):
        self._api = api

    def provide(self, name: str, service: Any) -> None:
        services = self._api._host.services
        if name in services:
            raise PluginError(f"plugin {self._api.id}: service {name!r} already provided")
        services[name] = (self._api.id, service)
        self._api._record.record("services", name)
        self._api._cleanup.append(lambda: services.pop(name, None))

    def get(self, name: str) -> Any:
        entry = self._api._host.services.get(name)
        if entry is None:
            raise PluginError(f"plugin {self._api.id}: no service {name!r}")
        provider, service = entry
        if provider not in self._api._record.manifest.depends:
            raise PluginError(
                f"plugin {self._api.id} uses service {name!r} from {provider} without depending on it"
            )
        return service


class _Counters:
    """Engine counters (sage.world.counters): bump, publish CountersChanged, return player lines."""

    def __init__(self, api: PluginAPI):
        self._api = api

    async def count(
        self, player_id: str, stats: dict[str, Any], *names: str, delta: int = 1
    ) -> list[str]:
        from sage.world.counters import count

        return await count(self._api._host, player_id, stats, *names, delta=delta)


class _Inventory:
    """A character's carried items (engine hot state)."""

    def __init__(self, api: PluginAPI):
        self._api = api

    async def get(self, player_id: str) -> list[dict[str, Any]]:
        return list(await self._api._host.redis.get_player_inventory(player_id) or [])

    async def set(self, player_id: str, items: list[dict[str, Any]]) -> None:
        await self._api._host.redis.set_player_inventory(player_id, items)


class _Content:
    """Read-only, hot-reloading access to the world's content directories."""

    def __init__(self, api: PluginAPI):
        self._api = api

    def cached(self, subdir: str, loader: Callable[[Path], Any], pattern: str = "*.yaml") -> Any:
        """A DirCache over <world content_dir>/<subdir>; get() reloads when files change."""
        from sage.world.content_cache import DirCache

        return DirCache(Path(self._api._host.world.content_dir) / subdir, loader, pattern)

    def extend(self, kind: str, name: str, model: type) -> None:
        """Claim a YAML field on rooms, features, items or entities ("room", "shop", ShopModel)."""
        from sage.world.extensions import ExtensionError

        host = self._api._host
        try:
            host.extensions.register(kind, name, model, owner=self._api.id)
        except ExtensionError as exc:
            raise PluginError(f"plugin {self._api.id}: {exc}") from exc
        self._api._record.record("content_extensions", f"{kind}.{name}")
        self._api._cleanup.append(lambda: host.extensions.withdraw(self._api.id))

    def extension(self, obj: Any, kind: str, name: str) -> Any:
        """This plugin's validated block on a content object, or None."""
        host = self._api._host
        if host.extensions.owner(kind, name) != self._api.id:
            raise PluginError(f"plugin {self._api.id} reads {kind}.{name}, which it did not claim")
        return host.extensions.get(obj, kind, name)

    def room(self, room_id: str) -> Any:
        return self._api._host.content.get_room(room_id)

    def room_ids(self) -> list[str]:
        return self._api._host.content.list_room_ids()

    def item_template_ids(self) -> list[str]:
        return self._api._host.content.list_item_template_ids()

    def item_template(self, template_id: str) -> Any:
        return self._api._host.content.get_item_template(template_id)

    def entity_template(self, template_id: str) -> Any:
        return self._api._host.content.get_entity_template(template_id)


class _Http:
    """Plugin HTTP routes on Nexus (contracts catalog #9), mounted under /plugins/<id>/."""

    def __init__(self, api: PluginAPI):
        self._api = api

    def admin_router(self, router: Any, tool: str) -> None:
        """Mount router at /plugins/<id>/admin; every route needs a staff token and `tool`.

        The admin client lists the mount (GET /admin/plugin-pages) and opens the page it has for
        `tool` against this base URL, so the page shows only in worlds that enable the plugin.
        """
        from fastapi import Depends

        from sage.admin.route_helpers import require_tool

        app = self._api._host.http
        if app is None:
            self._api.log.info("no HTTP app in this host; admin routes not mounted")
            return
        try:
            guard = require_tool(tool)
        except ValueError as exc:
            raise PluginError(f"plugin {self._api.id}: {exc}") from exc
        before = list(app.router.routes)
        app.include_router(
            router, prefix=f"/plugins/{self._api.id}/admin", dependencies=[Depends(guard)]
        )
        added = [r for r in app.router.routes if r not in before]
        app.openapi_schema = None
        self._api._record.record("routes", f"/plugins/{self._api.id}/*")
        mount = (self._api.id, tool)
        self._api._host.admin_tools.append(mount)

        def unmount() -> None:
            app.router.routes[:] = [r for r in app.router.routes if r not in added]
            app.openapi_schema = None
            if mount in self._api._host.admin_tools:
                self._api._host.admin_tools.remove(mount)

        self._api._cleanup.append(unmount)

    def play_router(self, router: Any) -> None:
        """Mount router at /plugins/<id>/play: public (player clients authenticate per request)."""
        app = self._api._host.http
        if app is None:
            self._api.log.info("no HTTP app in this host; play routes not mounted")
            return
        before = list(app.router.routes)
        app.include_router(router, prefix=f"/plugins/{self._api.id}/play")
        added = [r for r in app.router.routes if r not in before]
        app.openapi_schema = None
        self._api._record.record("routes", f"/plugins/{self._api.id}/*")

        def unmount() -> None:
            app.router.routes[:] = [r for r in app.router.routes if r not in added]
            app.openapi_schema = None

        self._api._cleanup.append(unmount)


class _Redis:
    """Plugin-owned Redis keys: "<prefix>" or "<prefix>:..." for a declared redis_prefixes."""

    COMMANDS = frozenset(
        {
            "get",
            "set",
            "delete",
            "getdel",
            "incrby",
            "expire",
            "hget",
            "hset",
            "hdel",
            "hgetall",
            "hincrby",
            "lpush",
            "ltrim",
            "lrange",
        }
    )

    def __init__(self, api: PluginAPI):
        self._api = api

    def _check(self, key: str) -> None:
        prefixes = self._api._record.manifest.touches.redis_prefixes
        if not any(key == p or key.startswith(f"{p}:") for p in prefixes):
            raise PluginError(
                f"plugin {self._api.id} used Redis key {key!r} outside its redis_prefixes {prefixes}"
            )

    def __getattr__(self, command: str) -> Callable[..., Any]:
        if command not in self.COMMANDS:
            raise AttributeError(f"plugin Redis surface has no command {command!r}")

        async def call(key: str, *args: Any, **kwargs: Any) -> Any:
            self._check(key)
            redis = self._api._host.redis
            return await getattr(redis.client, command)(redis.key(key), *args, **kwargs)

        return call


class _Telemetry:
    def __init__(self, api: PluginAPI):
        self._api = api

    def event(self, kind: str, /, **fields: Any) -> None:
        from sage.telemetry import log_event

        log_event(kind, **fields)

    async def heat(self, map_name: str, key: str, by: int = 1) -> None:
        from sage.telemetry import heat

        await heat(self._api._host.redis, map_name, key, by)

    async def read_heatmaps(self, names: list[str]) -> dict[str, dict[str, int]]:
        from sage.telemetry import read_heatmaps

        return await read_heatmaps(self._api._host.redis, names)


class _Progression:
    """Report skill use to the world's progression provider (sage.world.progression)."""

    def __init__(self, api: PluginAPI):
        self._api = api

    async def skill_used(self, player_id: str, skill: str | None, chance: float = 1.0) -> None:
        if skill:
            from sage.world.progression import SKILL_USED

            await self._api._host.resolvers.get(SKILL_USED)(player_id, skill, chance)

    def seed_attributes(self, stats: dict[str, Any], attributes: dict[str, int]) -> None:
        from sage.world.progression import SEED_ATTRIBUTES

        self._api._host.resolvers.get(SEED_ATTRIBUTES)(stats, attributes)

    def total_levels(self, stats: dict[str, Any]) -> int:
        from sage.world.progression import TOTAL_LEVELS

        return int(self._api._host.resolvers.get(TOTAL_LEVELS)(stats))

    def sheet(self, stats: dict[str, Any]) -> dict[str, Any]:
        from sage.world.progression import SKILL_SHEET

        return self._api._host.resolvers.get(SKILL_SHEET)(stats)

    def skill_level(self, stats: dict[str, Any], skill: str | None) -> int:
        if not skill:
            return 0
        from sage.world.progression import SKILL_LEVEL

        return int(self._api._host.resolvers.get(SKILL_LEVEL)(stats, skill))


class _Sessions:
    """Who is connected, and pushing their client state."""

    def __init__(self, api: PluginAPI):
        self._api = api

    def online(self) -> list[str]:
        return list(self._api._host.server.session_manager.player_to_session)

    def get(self, player_id: str) -> Any:
        return self._api._host.server.session_manager.get_session_by_player(player_id)

    async def push_snapshot(self, session: Any) -> None:
        push = getattr(self._api._host.server, "push_character_snapshot", None)
        if push is not None:
            await push(session)

    def attach(self, session: Any) -> None:
        """Register a (virtual) session so the world treats its character as connected."""
        manager = self._api._host.server.session_manager
        manager.sessions[session.id] = session
        manager.player_to_session[session.player_id] = session.id
        self._api._cleanup.append(lambda: self.detach(session.player_id))

    def detach(self, player_id: str) -> None:
        manager = self._api._host.server.session_manager
        session_id = manager.player_to_session.pop(player_id, None)
        if session_id is not None:
            manager.sessions.pop(session_id, None)

    async def dispatch(self, session: Any, line: str) -> None:
        """Run a command line as that session typed it."""
        await self._api._host.server.dispatcher.dispatch(session, line)


class _Entities:
    """Live entities (mobs, NPCs) in rooms."""

    def __init__(self, api: PluginAPI):
        self._api = api

    async def count_in_room(self, room_id: str, template_id: str) -> int:
        return await self._api._host.server.spawner.count_template_in_room(room_id, template_id)

    async def spawn(self, room_id: str, template_id: str) -> str | None:
        return await self._api._host.server.spawner.spawn_entity(room_id, template_id)

    async def state(self, entity_id: str) -> dict[str, Any] | None:
        return await self._api._host.redis.get_entity_state(entity_id)

    async def save(self, entity_id: str, state: dict[str, Any]) -> None:
        await self._api._host.redis.set_entity_state(entity_id, state)

    def lock(self, entity_id: str) -> Any:
        """An asyncio lock for one entity's read-modify-write (released on despawn)."""
        from sage.world.spawner import entity_lock

        return entity_lock(entity_id)

    async def kill(self, entity_id: str, room_id: str) -> list[dict[str, Any]]:
        """Drop an entity's loot on the floor and despawn it; returns the dropped items' states."""
        host = self._api._host
        dropped = await host.server.spawner.kill_entity(entity_id, room_id)
        states = [await host.redis.get_item_state(item_id) for item_id in dropped]
        return [s for s in states if s]


class _Items:
    """Items lying in rooms."""

    def __init__(self, api: PluginAPI):
        self._api = api

    async def place(self, room_id: str, template_id: str) -> dict[str, Any] | None:
        """Mint one item from a template onto a room's floor; None for an unknown template."""
        import uuid

        template = self._api._host.content.get_item_template(template_id)
        if template is None:
            return None
        item_id = f"{template.id}_{uuid.uuid4().hex[:8]}"
        item = {
            "id": item_id,
            "template": template.id,
            "name": template.name,
            "description": template.description,
            "value": template.value,
        }
        redis = self._api._host.redis
        await redis.set_item_state(item_id, item)
        await redis.add_item_to_room(item_id, room_id)
        return item


class _Effects:
    """Timed effects on a stats blob (sage.effects.engine): damage/heal over time and flags."""

    def __init__(self, api: PluginAPI):
        self._api = api

    def make(self, classification: str, **kwargs: Any) -> dict[str, Any]:
        from sage.effects.engine import make_effect

        return make_effect(classification, **kwargs)

    def apply(self, stats: dict[str, Any], effect: dict[str, Any]) -> None:
        from sage.effects.engine import apply_effect

        apply_effect(stats, effect)

    def find(self, stats: dict[str, Any], classification: str) -> list[dict[str, Any]]:
        from sage.effects.engine import find_effects

        return find_effects(stats, classification)

    def clear_on_death(self, stats: dict[str, Any]) -> None:
        from sage.effects.engine import clear_on_death

        clear_on_death(stats)

    def describe(self, stats: dict[str, Any]) -> list[str]:
        from sage.effects.engine import describe_effects

        return describe_effects(stats)

    async def advance(self, player_id: str) -> tuple[list[str], list[str], bool]:
        """Run a character's due effect ticks and expiries, saving the result.

        Returns (effect messages, death counter lines, died). A death here is recorded like any
        other (PlayerDied, counters, telemetry); what to tell the player is the caller's.
        """
        from sage.effects.death import record_player_death
        from sage.effects.engine import EFFECTS_KEY, process_effects

        host = self._api._host
        stats = await host.redis.get_player_stats(player_id)
        if not stats.get(EFFECTS_KEY):
            return [], [], False
        was_alive = int(stats.get("hp", 1)) > 0
        messages = process_effects(stats)
        if not messages and stats.get(EFFECTS_KEY):
            return [], [], False  # nothing fired, nothing expired: skip the write
        died = was_alive and int(stats.get("hp", 1)) <= 0
        lines: list[str] = []
        if died:
            session = host.server.session_manager.get_session_by_player(player_id)
            room_id = await host.redis.get_player_location(player_id)
            lines = await record_player_death(
                host.server, session, player_id, stats, room_id, "affliction"
            )
        await host.redis.set_player_stats(player_id, stats)
        return messages, lines, died


class _Characters:
    """Characters a plugin runs itself (automated characters): it owns their whole stats blob.

    record_death applies to any character.
    """

    def __init__(self, api: PluginAPI):
        self._api = api
        self._owned: set[str] = set()

    async def record_death(
        self, session: Any, player_id: str, stats: dict[str, Any], room_id: str | None, cause: str
    ) -> list[str]:
        """Record a death on a stats blob the caller holds (PlayerDied, counters, telemetry)."""
        from sage.effects.death import record_player_death

        return await record_player_death(
            self._api._host.server, session, player_id, stats, room_id, cause
        )

    def claim_names(self, names: Callable[[], Any]) -> None:
        """Player character creation refuses every name names() returns."""
        claims = self._api._host.name_claims
        entry = (self._api.id, names)
        claims.append(entry)
        self._api._cleanup.append(lambda: entry in claims and claims.remove(entry))

    async def place(
        self, name: str, stats: dict[str, Any], inventory: list[Any], room_id: str
    ) -> None:
        """Put an owned character into hot state (stats, inventory, location)."""
        self._owned.add(name)
        redis = self._api._host.redis
        await redis.set_player_stats(name, stats)
        await redis.set_player_inventory(name, inventory)
        await redis.set_player_location(name, room_id)

    async def remove(self, name: str) -> None:
        """Take an owned character out of its room (hot state is left for the next place)."""
        redis = self._api._host.redis
        room_id = await redis.get_player_location(name)
        if room_id:
            await redis.remove_player_from_room(name, room_id)
        self._owned.discard(name)

    def _check(self, name: str) -> None:
        if name not in self._owned:
            raise PluginError(f"plugin {self._api.id} writes character {name!r} it did not place")

    async def stats(self, name: str) -> dict[str, Any]:
        return await self._api._host.redis.get_player_stats(name)

    async def save_stats(self, name: str, stats: dict[str, Any]) -> None:
        self._check(name)
        await self._api._host.redis.set_player_stats(name, stats)

    async def move(self, name: str, room_id: str) -> None:
        self._check(name)
        await self._api._host.redis.set_player_location(name, room_id)


class _Rooms:
    """Who and what is in a room right now."""

    def __init__(self, api: PluginAPI):
        self._api = api

    async def players(self, room_id: str) -> list[str]:
        return [_text(p) for p in await self._api._host.redis.get_room_players(room_id)]

    async def entities(self, room_id: str) -> list[dict[str, Any]]:
        redis = self._api._host.redis
        states = [await redis.get_entity_state(e) for e in await redis.get_room_entities(room_id)]
        return [s for s in states if s]

    async def items(self, room_id: str) -> list[dict[str, Any]]:
        redis = self._api._host.redis
        states = [await redis.get_item_state(_text(i)) for i in await redis.get_room_items(room_id)]
        return [s for s in states if s]


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else value


class _Persistence:
    def __init__(self, api: PluginAPI):
        self._api = api

    def on_flush(self, hook: Callable[[], Any]) -> None:
        """Run an async hook on the engine's persistence cadence and at shutdown."""
        hooks = self._api._host.server.persistence.flush_hooks
        hooks.append(hook)
        self._api._cleanup.append(lambda: hook in hooks and hooks.remove(hook))

    def session(self) -> Any:
        """An async SQLAlchemy session for the plugin's own plg_<id>_* tables."""
        return self._api._host.server.db.session_factory()


class _Ai:
    def __init__(self, api: PluginAPI):
        self._api = api

    def slot(self, name: str) -> str:
        """Declare AI slot "<plugin>.<name>"; the world fills it with ai/prompts/<slot>.j2."""
        api = self._api
        slot = f"{api.id}.{name}"
        prompts = api._host.server.prompt_manager
        try:
            prompts.declare(slot, api.id)
        except ValueError as exc:
            raise PluginError(f"plugin {api.id}: {exc}") from exc
        api._record.record("ai_slots", slot)
        api._cleanup.append(lambda: prompts.withdraw(api.id))
        return slot

    def enabled(self, name: str) -> bool:
        """Whether the world fills this plugin's slot (callers skip AI work otherwise)."""
        return self._api._host.server.prompt_manager.enabled(f"{self._api.id}.{name}")

    async def narrate(self, name: str, max_tokens: int, **variables: Any) -> str:
        """Render this plugin's slot and generate with the narration LLM; raises on failure.

        Narration only colours what already happened: callers send their outcome first and
        treat any exception (including sage.llm.prompts.SlotDisabled) as "no prose".
        """
        server = self._api._host.server
        prompt = server.prompt_manager.render(f"{self._api.id}.{name}", **variables)
        return await server.llm_client.generate_or_raise(prompt, max_tokens=max_tokens)

    def profile(self, name: str = "agents_llm") -> Any:
        """The named LLM profile (sage.llm.profiles.LLMProfile); generate() raises on failure."""
        return self._api._host.server.llm_profile


class _Clock:
    def phase(self) -> str:
        from sage.world.clock import day_phase

        return day_phase()


class _Snapshot:
    def __init__(self, api: PluginAPI):
        self._api = api

    def contribute(self, section: str, fn: Callable[[str, dict[str, Any]], Any]) -> None:
        """Add a section to the client character snapshot: fn(character_name, stats) -> data."""
        contributors = self._api._host.server.snapshot_contributors
        try:
            contributors.add(section, fn, owner=self._api.id)
        except ValueError as exc:
            raise PluginError(f"plugin {self._api.id}: {exc}") from exc
        self._api._record.record("snapshot", section)
        self._api._cleanup.append(lambda: contributors.withdraw(self._api.id))


class _Ui:
    def __init__(self, api: PluginAPI):
        self._api = api

    def panel(self, name: str, kind: str, section: str, icon: str = "") -> None:
        """Declare player panel "<plugin>.<name>" drawing one of this plugin's snapshot sections.

        Kinds and data shapes: sage.network.panels. The title is lexicon "<plugin>.panel.<name>".
        """
        from sage.network.panels import Panel

        api = self._api
        if section not in api._record.registered.get("snapshot", set()):
            raise PluginError(
                f"plugin {api.id}: panel {name!r} reads section {section!r}, which it does not "
                "contribute (call api.snapshot.contribute first)"
            )
        panels = api._host.server.panels
        panel = Panel(id=f"{api.id}.{name}", owner=api.id, kind=kind, section=section, icon=icon)
        try:
            panels.add(panel)
        except ValueError as exc:
            raise PluginError(f"plugin {api.id}: {exc}") from exc
        api._record.record("panels", panel.id)
        api._cleanup.append(lambda: panels.withdraw(api.id))


class PluginAPI:
    def __init__(self, host: Any, record: Any):
        self._host = host
        self._record = record
        self._cleanup: list[Callable[[], Any]] = []
        self.id: str = record.id
        self.log = logging.getLogger(f"sage.plugin.{record.id}")
        self.commands = _Commands(self)
        self.events = _Events(self)
        self.resolvers = _Resolvers(self)
        self.tick = _Tick(self)
        self.state = _State(self)
        self.services = _Services(self)
        self.counters = _Counters(self)
        self.inventory = _Inventory(self)
        self.content = _Content(self)
        self.http = _Http(self)
        self.redis = _Redis(self)
        self.telemetry = _Telemetry(self)
        self.progression = _Progression(self)
        self.sessions = _Sessions(self)
        self.entities = _Entities(self)
        self.items = _Items(self)
        self.effects = _Effects(self)
        self.characters = _Characters(self)
        self.rooms = _Rooms(self)
        self.persistence = _Persistence(self)
        self.ai = _Ai(self)
        self.clock = _Clock()
        self.snapshot = _Snapshot(self)
        self.ui = _Ui(self)

    @property
    def world(self) -> Any:
        return self._host.world

    @property
    def wallet(self) -> Any:
        """The engine wallet over this world's currencies (sage.world.wallet.Wallet)."""
        from sage.world.wallet import Wallet

        return Wallet(self._host.world, self._host.redis)

    def param(self, key: str, default: Any = None) -> Any:
        """A world param namespaced to this plugin: "<plugin id>.<key>"."""
        return self._host.world.param(f"{self.id}.{key}", default)

    def t(self, key: str, **variables: Any) -> str:
        return lexicon.t(key, **variables)

    def lexicon_keys(self, prefix: str) -> list[str]:
        """Every resolvable key under prefix, sorted — lets worlds add numbered lines."""
        return sorted(k for k in lexicon.active().keys() if k.startswith(prefix))

    def withdraw(self) -> None:
        """Undo every registration (setup failure or teardown)."""
        self._host.events.unsubscribe_owner(self.id)
        for undo in reversed(self._cleanup):
            try:
                undo()
            except Exception:
                self.log.debug("cleanup step failed", exc_info=True)
        self._cleanup.clear()
