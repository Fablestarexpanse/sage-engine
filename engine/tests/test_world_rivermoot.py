"""The second reference world and its levels plugin, loaded through the real plugin host."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sage import lexicon
from sage.commands.registry import CommandRegistry
from sage.core.events import EntityKilled, EventBus
from sage.core.resolvers import Resolvers
from sage.core.tick import TickManager
from sage.plugins import PluginHost
from sage.world.package import load_world_package
from tests.fakes import FakeRedis, StubSession

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def rivermoot():
    world = load_world_package(ROOT / "worlds" / "rivermoot")
    host = PluginHost(
        world=world,
        registry=CommandRegistry(),
        events=EventBus(),
        resolvers=Resolvers(),
        tick_manager=TickManager(),
        redis=FakeRedis(),
        plugins_root=ROOT / "plugins",
        trusted_roots=[ROOT / "plugins", ROOT / "worlds"],
    )
    host.load()
    previous = lexicon.active()
    lexicon.set_active(
        lexicon.build_lexicon(world.lexicon_dir, plugin_layers=host.lexicon_layers())
    )
    yield world, host
    lexicon.set_active(previous)
    host.teardown()
    for name in [m for m in sys.modules if m.startswith("sage_worlds.rivermoot")]:
        del sys.modules[name]


def test_world_differs_from_the_first_reference_world(rivermoot):
    world, host = rivermoot
    assert [a.key for a in world.stats.attributes] == ["mgt", "wts", "nrv"]
    assert [c.key for c in world.currencies] == ["silver"]
    # combat without equipment: its optional dependency is simply absent here.
    assert [r.id for r in host.loaded] == ["combat", "levels"]
    assert (world.content_dir / "world" / "zones" / "town" / "rooms" / "bridge.yaml").is_file()


def test_world_lexicon_overrides_engine_defaults(rivermoot):
    assert "Rivermoot" in lexicon.t("login.banner")
    assert lexicon.t("who.empty").startswith("The square is empty")
    assert lexicon.t("stat.nrv.name") == "Nerve"


def test_kills_grant_experience_and_levels(rivermoot):
    world, host = rivermoot
    stats: dict = {}

    async def kill():
        event = EntityKilled(
            killer_id="hero",
            entity_id="rat_1",
            template="river_rat",
            room_id="town:market",
            stats=stats,
        )
        await host.events.publish(event)
        return event.messages

    assert asyncio.run(kill()) == ["You gain 5 experience."]
    assert stats["levels"] == {"level": 1, "xp": 5}
    assert asyncio.run(kill()) == ["You gain 5 experience.", "You are now level 2!"]
    assert stats["levels"] == {"level": 2, "xp": 0}


def test_level_command_reads_the_state_block(rivermoot):
    world, host = rivermoot

    async def run():
        await host.redis.set_player_stats("hero", {"levels": {"level": 3, "xp": 4}})
        session = StubSession("hero")
        await host.registry.get("lvl").handler(session, [])
        return session.sent

    assert asyncio.run(run()) == ["Level 3  (4/30 experience)"]
