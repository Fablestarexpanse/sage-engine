"""PluginAPI: the scoped surface a plugin's ``setup(api)`` receives (contracts C.4, C.5).

Every registration is tagged with the plugin id and recorded so the loader can seal the plugin
against its manifest and withdraw everything if setup fails or the plugin is torn down.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
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
        import copy

        return copy.deepcopy(await self._api._host.redis.get_player_stats(player_id))

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
