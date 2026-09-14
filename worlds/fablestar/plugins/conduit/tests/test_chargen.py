"""Chargen starter allocation accepts whole numbers only (live QA: floats, bools, Infinity)."""

from __future__ import annotations

import math

import pytest
from sage_plugin_conduit.catalog_loader import load_proficiency_catalog_from_disk
from sage_plugin_conduit.main import clean_allocation
from sage_plugin_conduit.registry import ProficiencyRegistry
from sage_plugin_conduit.starter import coerce_starter_level
from tests.fakes import repo_world

LEAF = "combat.melee.blades"


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        (3, 3),
        (2.0, 2),
        (0, 0),
        (-1, -1),
        (2.7, None),
        (5.9, None),
        (-0.5, None),
        (True, None),
        (False, None),
        ("3", None),
        (None, None),
        ([3], None),
        (math.nan, None),
        (math.inf, None),
        (-math.inf, None),
    ],
)
def test_coerce_starter_level(raw, want):
    assert coerce_starter_level(raw) == want


REGISTRY = ProficiencyRegistry(load_proficiency_catalog_from_disk(repo_world().content_dir).leaves)


def _clean(alloc):
    error, cleaned = clean_allocation({"proficiencies": alloc}, REGISTRY)
    return ({"ok": False, "error": error} if error else None), cleaned


def test_whole_numbers_accepted():
    err, clean = _clean({LEAF: 3, "combat.melee.impact": 2.0})
    assert err is None and clean == {LEAF: 3, "combat.melee.impact": 2}


@pytest.mark.parametrize("bad", [2.7, 5.9, True, "3", math.inf, -math.inf, math.nan, None])
def test_non_integers_refused_not_truncated(bad):
    err, clean = _clean({LEAF: bad})
    assert err == {"ok": False, "error": "invalid_starter_proficiencies"} and clean == {}


def test_duplicate_key_after_trim_refused():
    err, _ = _clean({LEAF: 5, f" {LEAF}": 1})
    assert err == {"ok": False, "error": "invalid_starter_proficiencies"}


def test_limits_still_enforced():
    err, _ = _clean({LEAF: 6})
    assert err["error"] == f"level_out_of_range:{LEAF}"


def test_plugin_provides_chargen_prepare_and_ratings_through_the_host(plugin_host):
    import asyncio

    from tests.fakes import StubSession

    host = plugin_host(repo_world(), ["conduit"])
    validate = host.resolvers.get("chargen.validate")
    assert validate({"proficiencies": {LEAF: 3}}) == (None, {LEAF: 3})
    assert validate({"proficiencies": {LEAF: 2.5}})[0] == "invalid_starter_proficiencies"

    stats = host.resolvers.get("progression.prepare")({"strength": 16})
    host.resolvers.get("chargen.seed")(stats, {LEAF: 3})
    assert stats["conduit"]["proficiencies"][LEAF]["level"] == 3
    assert host.resolvers.get("progression.total_levels")(stats) >= 3
    attack, defense = host.resolvers.get("combat.ratings")(stats)
    assert attack >= 1 and defense >= 1

    host.redis.stats["hero"] = stats
    session = StubSession("hero")
    asyncio.run(host.registry.get("score").handler(session, []))
    assert "Top proficiencies:" in session.sent[0]


def test_options_declare_the_skill_points_kind(plugin_host):
    """The player client renders a choices step only for a kind it knows."""
    host = plugin_host(repo_world(), ["conduit"])
    options = host.resolvers.get("chargen.options")()
    assert options["kind"] == "skill_points"
    assert options["title"] == "Starting proficiencies"
    assert options["budget"] > 0 and options["max_per_leaf"] > 0 and options["leaves"]
