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
    from sage.world.slots import define_engine_slots

    define_engine_slots(host.resolvers, world)
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
    assert sorted(r.id for r in host.loaded) == [
        "ambient",
        "combat",
        "consumables",
        "effects",
        "equipment",
        "hazards",
        "levels",
        "lodging",
        "search",
        "shop",
    ]
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

    stats.update({"hp": 5, "max_hp": 12})
    assert asyncio.run(kill()) == ["You gain 5 experience."]
    assert stats["levels"] == {"level": 1, "xp": 5}
    assert asyncio.run(kill()) == [
        "You gain 5 experience.",
        "You are now level 2! (+2 maximum health)",
    ]
    assert stats["levels"] == {"level": 2, "xp": 0}
    assert (stats["hp"], stats["max_hp"]) == (7, 14)


def test_combat_ratings_come_from_might_nerve_and_level(rivermoot):
    world, host = rivermoot
    rate = host.resolvers.get("combat.ratings")
    assert rate({"mgt": 2, "nrv": 2}) == (2, 1)
    assert rate({"mgt": 4, "nrv": 5, "levels": {"level": 3, "xp": 0}}) == (5, 3)
    assert host.resolvers.get("progression.total_levels")({"levels": {"level": 4}}) == 4


def test_levels_panel_is_a_stat_sheet(rivermoot):
    world, host = rivermoot
    assert ("levels.sheet", "stat_sheet", "Level") in [
        (p["id"], p["kind"], p["title"]) for p in host.server.panels.specs()
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


def test_attribute_point_buy_from_stats_yaml():
    """A stats.yaml with attribute_points gets engine chargen choices without any plugin."""
    from sage.world.slots import define_engine_slots

    world = load_world_package(ROOT / "worlds" / "rivermoot")
    resolvers = Resolvers()
    define_engine_slots(resolvers, world)
    options = resolvers.get("chargen.options")()
    assert options["kind"] == "attribute_points" and options["budget"] == 8
    assert [
        (a["key"], a["label"], a["min"], a["max"], a["default"]) for a in options["attributes"]
    ] == [
        ("mgt", "[stat.mgt.name]", 1, 6, 2),
        ("wts", "[stat.wts.name]", 1, 6, 2),
        ("nrv", "[stat.nrv.name]", 1, 6, 2),
    ]

    validate = resolvers.get("chargen.validate")
    assert validate({}) == (None, {})
    assert validate({"attributes": {"mgt": 4}}) == (
        None,
        {"attributes": {"mgt": 4, "wts": 2, "nrv": 2}},
    )
    assert validate({"attributes": {"mgt": 4, "wts": 3}})[0] == "attribute_budget_exceeded"
    assert validate({"attributes": {"mgt": 7}})[0] == "attribute_out_of_range:mgt"
    assert validate({"attributes": {"luck": 3}})[0] == "unknown_attribute:luck"
    assert validate({"attributes": {"mgt": 2.5}})[0] == "invalid_attributes"
    assert validate({"attributes": {"mgt": True}})[0] == "invalid_attributes"

    stats = {"mgt": 2, "wts": 2, "nrv": 2}
    resolvers.get("chargen.seed")(stats, validate({"attributes": {"mgt": 1, "nrv": 5}})[1])
    assert stats == {"mgt": 1, "wts": 2, "nrv": 5}


def test_worlds_without_attribute_points_keep_empty_chargen_defaults():
    from sage.world.slots import define_engine_slots

    resolvers = Resolvers()
    define_engine_slots(resolvers)
    assert resolvers.get("chargen.options")() == {}


def test_a_kill_inside_combats_edit_may_raise_maximum_health(rivermoot):
    """levels declares max_hp, so combat's blob may carry the level-up it published; nothing else."""
    from sage.plugins.manifest import PluginError

    world, host = rivermoot
    combat = next(r.api for r in host.loaded if r.id == "combat")
    host.redis.stats["hero"] = {"hp": 5, "max_hp": 12, "wts": 2}

    async def level_up():
        async with combat.state.edit("hero") as stats:
            stats["max_hp"], stats["hp"] = 14, 7

    asyncio.run(level_up())
    assert host.redis.stats["hero"]["max_hp"] == 14

    async def scribble():
        async with combat.state.edit("hero") as stats:
            stats["wts"] = 6

    with pytest.raises(PluginError, match="does not own"):
        asyncio.run(scribble())
    assert host.redis.stats["hero"]["wts"] == 2


def test_world_content_lints_clean():
    """30 rooms in three zones, every exit two-way and in world.toml's directions, every template real."""
    from sage.world.lint import lint_world

    report = lint_world(load_world_package(ROOT / "worlds" / "rivermoot"))
    assert report.errors == [] and report.warnings == []
    assert len(report.rooms) == 30
    assert {room.zone for room in report.rooms.values()} == {"town", "riverside", "millward"}


def test_lint_reports_broken_content(tmp_path):
    import shutil

    from sage.world.lint import lint_world

    world = load_world_package(ROOT / "worlds" / "rivermoot")
    content = tmp_path / "content"
    shutil.copytree(world.content_dir, content)
    market = content / "world" / "zones" / "town" / "rooms" / "market.yaml"
    text = market.read_text(encoding="utf-8").replace("town:shrine", "town:nowhere")
    market.write_text(text.replace("template: river_rat", "template: dragon"), encoding="utf-8")
    report = lint_world(world.with_content_dir(content))
    assert "town:market east: destination 'town:nowhere' does not exist" in report.errors
    assert "town:market: spawns unknown entity 'dragon'" in report.errors
    assert "town:shrine west -> town:market, which does not lead back" in report.warnings
