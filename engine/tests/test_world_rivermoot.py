"""The second reference world and its levels plugin, loaded through the real plugin host."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sage import lexicon
from sage.commands.registry import CommandRegistry
from sage.core.events import EntityKilled, EventBus
from sage.core.resolvers import Resolvers
from sage.core.tick import TickManager
from sage.llm.prompts import PromptManager
from sage.network.panels import PanelRegistry
from sage.network.snapshot import SnapshotContributors
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
    host.server = SimpleNamespace(
        snapshot_contributors=SnapshotContributors(),
        panels=PanelRegistry(),
        prompt_manager=PromptManager(world.prompts_dir),
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


def test_levels_panel_is_a_stat_sheet(rivermoot):
    world, host = rivermoot
    assert [(p["id"], p["kind"], p["title"]) for p in host.server.panels.specs()] == [
        ("levels.sheet", "stat_sheet", "Level")
    ]
    sections = asyncio.run(
        host.server.snapshot_contributors.build("hero", {"levels": {"level": 2, "xp": 3}})
    )
    assert sections["levels"] == {
        "stats": [{"label": "Level", "value": 2}, {"label": "Experience", "value": 3, "max": 20}]
    }


def test_level_command_reads_the_state_block(rivermoot):
    world, host = rivermoot

    async def run():
        await host.redis.set_player_stats("hero", {"levels": {"level": 3, "xp": 4}})
        session = StubSession("hero")
        await host.registry.get("lvl").handler(session, [])
        return session.sent

    assert asyncio.run(run()) == ["Level 3  (4/30 experience)"]


def test_stat_schema_seeds_attributes_and_vitals():
    """stats.yaml is applied: the world's attributes at their defaults and full vitals."""
    from sage.world.death import default_respawn
    from sage.world.package import vital_max
    from sage.world.progression import default_seed_attributes

    world = load_world_package(ROOT / "worlds" / "rivermoot")
    assert world.attribute_defaults() == {"mgt": 2, "wts": 2, "nrv": 2}
    stats: dict = {}
    default_seed_attributes(stats, world.attribute_defaults())
    world.seed_vitals(stats)
    assert stats == {"mgt": 2, "wts": 2, "nrv": 2, "max_hp": 12, "hp": 12}

    wounded = {"hp": 3, "max_hp": 20}
    world.seed_vitals(wounded)
    assert wounded == {"hp": 3, "max_hp": 20}
    assert vital_max(world, "hp", 99) == 12 and vital_max(object(), "hp", 99) == 99
    assert default_respawn(world, {}, wallet=0).hp == 6
