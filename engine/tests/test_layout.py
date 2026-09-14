"""Room positions from exits for zones without editor layout."""

from __future__ import annotations

from pathlib import Path

from sage.world.layout import STEP_X, STEP_Y, layout_from_exits
from sage.world.lint import lint_world
from sage.world.package import load_world_package

ROOT = Path(__file__).resolve().parents[2]


def test_neighbours_sit_one_step_away_in_their_direction():
    exits = {"a": {"north": "b", "east": "c"}, "b": {"south": "a"}, "c": {"west": "a"}}
    pos = layout_from_exits(exits)
    ax, ay = pos["a"]
    assert pos["b"] == (ax, ay - STEP_Y)
    assert pos["c"] == (ax + STEP_X, ay)


def test_stored_positions_win_and_collisions_step_outward():
    exits = {"a": {"north": "b"}, "b": {"south": "a"}, "c": {"south": "a"}}
    pos = layout_from_exits(exits, {"a": (0.0, 0.0), "b": (0.0, -STEP_Y)})
    assert pos["a"] == (0.0, 0.0) and pos["b"] == (0.0, -STEP_Y)
    assert pos["c"] not in (pos["a"], pos["b"])


def test_a_whole_world_gets_distinct_spots():
    report = lint_world(load_world_package(ROOT / "worlds" / "rivermoot"))
    for zone in {r.zone for r in report.rooms.values()}:
        rooms = {rid.partition(":")[2]: r for rid, r in report.rooms.items() if r.zone == zone}
        graph = {
            slug: {
                d: e.destination.partition(":")[2]
                for d, e in r.exits.items()
                if e.destination.startswith(f"{zone}:")
            }
            for slug, r in rooms.items()
        }
        pos = layout_from_exits(graph)
        assert set(pos) == set(rooms)
        assert len(set(pos.values())) == len(pos), zone
