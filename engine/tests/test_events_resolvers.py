"""Event bus, resolver slots, tick jobs and the default death policy (contracts D.B)."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from sage.commands.registry import command, registry
from sage.core.events import CommandExecuted, EntityKilled, EventBus, PlayerDied, emit
from sage.core.resolvers import ResolverError, Resolvers
from sage.core.tick import TickManager
from sage.parser.dispatcher import CommandDispatcher
from sage.world.death import (
    PARAM_RESPAWN_BILL_MAX,
    PARAM_RESPAWN_HP_FRACTION,
    default_death_check,
    default_respawn,
)
from tests.fakes import StubSession, repo_world


def test_bus_calls_sync_and_async_subscribers_in_order():
    bus = EventBus()
    seen: list[str] = []

    def first(event):
        seen.append("first")

    async def second(event):
        seen.append("second")

    bus.subscribe(PlayerDied, first, owner="sage")
    bus.subscribe(PlayerDied, second, owner="plugin_a")
    asyncio.run(bus.publish(PlayerDied(player_id="p", room_id=None, cause="test")))
    assert seen == ["first", "second"]
    assert bus.subscribers(PlayerDied) == ["sage", "plugin_a"]


def test_failing_subscriber_is_logged_and_does_not_stop_others(caplog):
    bus = EventBus()
    seen: list[str] = []

    def broken(event):
        raise RuntimeError("subscriber bug")

    async def broken_async(event):
        raise RuntimeError("async subscriber bug")

    bus.subscribe(PlayerDied, broken, owner="plugin_x")
    bus.subscribe(PlayerDied, broken_async, owner="plugin_y")
    bus.subscribe(PlayerDied, lambda e: seen.append("ok"))
    with caplog.at_level(logging.ERROR, logger="sage.core.events"):
        asyncio.run(bus.publish(PlayerDied(player_id="p", room_id=None, cause="test")))
    assert seen == ["ok"]
    assert "plugin_x" in caplog.text and "plugin_y" in caplog.text


def test_subscribers_can_enrich_events_and_owners_unsubscribe():
    bus = EventBus()

    def add_line(event: EntityKilled):
        event.messages.append("+1 reputation")
        event.stats["kills"] = event.stats.get("kills", 0) + 1

    bus.subscribe(EntityKilled, add_line, owner="factions")
    event = EntityKilled(killer_id="p", entity_id="e1", template="rat", room_id="z:r", stats={})
    asyncio.run(emit(SimpleNamespace(events=bus), event))
    assert event.messages == ["+1 reputation"] and event.stats == {"kills": 1}
    bus.unsubscribe_owner("factions")
    assert bus.subscribers(EntityKilled) == []
    asyncio.run(emit(SimpleNamespace(), event))  # no bus: a no-op, not an error


def test_resolver_default_provider_and_conflicts():
    resolvers = Resolvers()
    resolvers.define("combat.resolve", lambda: "default", owner="combat")
    assert resolvers.get("combat.resolve")() == "default"
    resolvers.provide("combat.resolve", lambda: "world rule", owner="world_rules")
    assert resolvers.get("combat.resolve")() == "world rule"
    assert resolvers.owner("combat.resolve") == "world_rules"
    with pytest.raises(ResolverError, match="already provided by 'world_rules'"):
        resolvers.provide("combat.resolve", lambda: "other", owner="levels")
    with pytest.raises(ResolverError, match="already defined"):
        resolvers.define("combat.resolve", lambda: None)
    with pytest.raises(ResolverError, match="unknown"):
        resolvers.provide("nope", lambda: None, owner="x")
    resolvers.withdraw("world_rules")
    assert resolvers.get("combat.resolve")() == "default"


def test_tick_every_runs_on_interval():
    async def run():
        tm = TickManager(tick_rate=0.001)
        seen: list[int] = []

        async def job(tick: int) -> None:
            seen.append(tick)

        async def stopper(tick: int) -> None:
            if tick >= 9:
                tm.stop()

        wrapper = tm.every(0.003, job, name="probe_job")
        tm.register(stopper)
        await asyncio.wait_for(tm.run(), timeout=2.0)
        assert seen == [3, 6, 9]
        assert wrapper.__qualname__ == "probe_job"
        tm.unregister(wrapper)
        assert wrapper not in tm._handlers

    asyncio.run(run())


class _World:
    respawn_room = "town:temple"

    def __init__(self, **params):
        self._params = params

    def param(self, key, default=None):
        return self._params.get(key, default)


def test_default_death_policy_is_free_and_half_health():
    assert default_death_check({"hp": 0}) and not default_death_check({"hp": 3})
    plan = default_respawn(_World(), {"max_hp": 40}, wallet=99)
    assert (plan.room_id, plan.hp, plan.bill) == ("town:temple", 20, 0)


def test_world_params_tune_the_default_policy():
    world = _World(**{PARAM_RESPAWN_BILL_MAX: 10, PARAM_RESPAWN_HP_FRACTION: 0.25})
    assert default_respawn(world, {"max_hp": 40}, wallet=7).bill == 7
    assert default_respawn(world, {"max_hp": 40}, wallet=50).bill == 10
    assert default_respawn(world, {"max_hp": 40}, wallet=50).hp == 10


def test_repository_world_keeps_its_respawn_bill():
    world = repo_world()
    assert world.param(PARAM_RESPAWN_BILL_MAX) == 10


def test_dispatcher_publishes_command_executed():
    bus = EventBus()
    seen: list[CommandExecuted] = []
    bus.subscribe(CommandExecuted, seen.append)
    saved = dict(registry._commands), dict(registry._aliases)

    @command("zzevent")
    async def zzevent(session, args):
        """probe"""

    try:
        session = StubSession()
        asyncio.run(CommandDispatcher(events=bus).dispatch(session, "zzevent one two"))
        assert [(e.player_id, e.verb, e.args) for e in seen] == [
            ("tester", "zzevent", ["one", "two"])
        ]
    finally:
        registry._commands, registry._aliases = saved
