"""Snapshot contributors: ordered sections, failures isolated, plugin registration sealed."""

import asyncio
from types import SimpleNamespace

import pytest

from sage.core.resolvers import Resolvers
from sage.network.snapshot import SnapshotContributors, progression_section
from sage.world.slots import define_engine_slots


def test_sections_build_in_order_and_skip_failures():
    contributors = SnapshotContributors()
    contributors.add("first", lambda name, stats: {"hp": stats["hp"]}, owner="a")

    async def slow(name, stats):
        return name.upper()

    contributors.add("second", slow, owner="b")
    contributors.add("broken", lambda name, stats: 1 / 0, owner="c")
    built = asyncio.run(contributors.build("pam", {"hp": 3}))
    assert built == {"first": {"hp": 3}, "second": "PAM"}
    assert contributors.sections() == ["first", "second", "broken"]
    with pytest.raises(ValueError, match="already contributed"):
        contributors.add("first", lambda n, s: None, owner="d")
    contributors.withdraw("c")
    assert contributors.sections() == ["first", "second"]


def test_engine_progression_section_uses_the_world_slot():
    resolvers = Resolvers()
    define_engine_slots(resolvers)
    section = progression_section(resolvers)
    assert section("pam", {}) == {"levels_total": 0}
    resolvers.provide("progression.total_levels", lambda stats: 7, owner="levels")
    assert section("pam", {}) == {"levels_total": 7}


def test_plugin_contributes_a_section():
    from sage.core.events import EventBus
    from sage.plugins.api import PluginAPI

    contributors = SnapshotContributors()
    record = SimpleNamespace(id="levels", record=lambda kind, name: None)
    host = SimpleNamespace(
        events=EventBus(), server=SimpleNamespace(snapshot_contributors=contributors)
    )
    api = PluginAPI(host, record)
    api.snapshot.contribute("levels", lambda name, stats: {"level": 2})
    assert asyncio.run(contributors.build("pam", {})) == {"levels": {"level": 2}}
    api.withdraw()
    assert contributors.sections() == []


def test_engine_slot_defaults_let_a_world_run_without_progression_or_chargen():
    from sage.world.chargen import SEED, VALIDATE
    from sage.world.progression import PREPARE
    from sage.world.ratings import RATINGS

    resolvers = Resolvers()
    define_engine_slots(resolvers)
    stats = {"might": 16, "wits": 10}
    assert resolvers.get(PREPARE)(stats) is stats
    # No world attribute means anything to the engine: flat ratings until a plugin provides them.
    assert resolvers.get(RATINGS)(stats) == (3, 2)
    assert resolvers.get(RATINGS)({}) == (3, 2)
    assert resolvers.get(VALIDATE)({"anything": 1}) == (None, {})
    assert resolvers.get(SEED)(stats, {}) is None


def test_plugin_play_routes_are_public_admin_routes_are_not():
    from sage.admin.admin_security import is_public_admin_path

    assert is_public_admin_path("/plugins/levels/play/sheet")
    assert not is_public_admin_path("/plugins/levels/admin/sheet")
    assert not is_public_admin_path("/plugins/play")
