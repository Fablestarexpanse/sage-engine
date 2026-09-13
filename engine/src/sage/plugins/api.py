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
    from sage.world.counters import COUNTERS_KEY, VISITED_KEY

    return {COUNTERS_KEY, VISITED_KEY, *(c.key for c in getattr(world, "currencies", []) or [])}


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
        )
        changed = {k for k in set(before) | set(stats) if before.get(k) != stats.get(k)}
        stray = sorted(changed - allowed)
        if stray:
            raise PluginError(f"plugin {self._api.id} changed stats it does not own: {stray}")
        await redis.set_player_stats(player_id, stats)

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
        """Claim a YAML field on rooms, items or entities ("room", "shop", ShopModel)."""
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

    def item_template(self, template_id: str) -> Any:
        return self._api._host.content.get_item_template(template_id)

    def entity_template(self, template_id: str) -> Any:
        return self._api._host.content.get_entity_template(template_id)


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

    @property
    def world(self) -> Any:
        return self._host.world

    @property
    def wallet(self) -> Any:
        """The engine wallet over this world's currencies (sage.world.wallet.Wallet)."""
        from sage.world.wallet import Wallet

        return Wallet(self._host.world)

    def param(self, key: str, default: Any = None) -> Any:
        """A world param namespaced to this plugin: "<plugin id>.<key>"."""
        return self._host.world.param(f"{self.id}.{key}", default)

    def t(self, key: str, **variables: Any) -> str:
        return lexicon.t(key, **variables)

    def withdraw(self) -> None:
        """Undo every registration (setup failure or teardown)."""
        self._host.events.unsubscribe_owner(self.id)
        for undo in reversed(self._cleanup):
            try:
                undo()
            except Exception:
                self.log.debug("cleanup step failed", exc_info=True)
        self._cleanup.clear()
