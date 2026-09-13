"""Ambient room-chat model and scheduling helpers."""

import random

import pytest
from pydantic import ValidationError

from sage.world.ambient import next_due, pick_line
from sage.world.models import AmbientModel, RoomModel


def _ambient(**overrides) -> AmbientModel:
    base = {"lines": ["a", "b", "c"], "min_interval": 10, "max_interval": 20}
    base.update(overrides)
    return AmbientModel(**base)


def test_room_model_accepts_ambient_block():
    room = RoomModel(
        id="z:r",
        zone="z",
        type="hub",
        ambient={"lines": ["The vents rattle."]},
    )
    assert room.ambient is not None
    assert room.ambient.lines == ["The vents rattle."]
    assert room.ambient.min_interval == 45.0


def test_room_model_ambient_defaults_to_none():
    room = RoomModel(id="z:r", zone="z", type="hub")
    assert room.ambient is None


def test_ambient_requires_at_least_one_line():
    with pytest.raises(ValidationError):
        AmbientModel(lines=[])


def test_pick_line_avoids_immediate_repeat():
    rng = random.Random(42)
    amb = _ambient()
    last = "a"
    for _ in range(50):
        line = pick_line(amb, last, rng)
        assert line != last
        last = line


def test_pick_line_single_line_may_repeat():
    rng = random.Random(1)
    amb = _ambient(lines=["only"])
    assert pick_line(amb, "only", rng) == "only"


def test_next_due_within_interval():
    rng = random.Random(7)
    amb = _ambient(min_interval=10, max_interval=20)
    for _ in range(50):
        due = next_due(amb, 100.0, rng)
        assert 110.0 <= due <= 120.0


def test_next_due_handles_swapped_bounds():
    rng = random.Random(7)
    amb = _ambient(min_interval=20, max_interval=10)
    due = next_due(amb, 0.0, rng)
    assert 10.0 <= due <= 20.0
