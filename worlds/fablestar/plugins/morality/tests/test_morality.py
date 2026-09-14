"""Morality through the host: the standing panel, clamped to its range, with a band note."""

from __future__ import annotations

import asyncio

from sage_plugin_morality.main import band_of, standing_of
from tests.fakes import repo_world


def test_standing_clamps_and_bands():
    assert standing_of({}) == 0
    assert standing_of({"morality": {"standing": 250}}) == 100
    assert [band_of(v) for v in (-100, -60, -59, 0, 19, 20, 60, 100)] == [
        "evil",
        "evil",
        "dark",
        "neutral",
        "neutral",
        "decent",
        "good",
        "good",
    ]


def test_panel_is_a_ranged_stat_sheet(plugin_host):
    host = plugin_host(repo_world(), ["morality"])
    [spec] = host.server.panels.specs()
    assert (spec["id"], spec["kind"], spec["title"]) == (
        "morality.standing",
        "stat_sheet",
        "Morality",
    )
    sections = asyncio.run(
        host.server.snapshot_contributors.build("hero", {"morality": {"standing": -70}})
    )
    assert sections["morality"] == {
        "stats": [
            {
                "label": "Moral standing",
                "value": -70,
                "min": -100,
                "max": 100,
                "note": "Evil",
                "tone": "bad",
            }
        ]
    }
