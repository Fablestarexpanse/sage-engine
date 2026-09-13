"""Chargen starter allocation accepts whole numbers only (live QA: floats, bools, Infinity)."""

from __future__ import annotations

import math

import pytest

from fablestar.proficiencies.starter import coerce_starter_level
from fablestar.services.player_service import PlayerService
from tests.fakes import make_fake_server

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


def _clean(alloc):
    return PlayerService(make_fake_server())._clean_starter_proficiencies(alloc)


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
