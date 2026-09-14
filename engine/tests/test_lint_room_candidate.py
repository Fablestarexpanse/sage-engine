"""A room is checked against its world before AI Forge writes it (sage.world.lint.lint_room_candidate)."""

from __future__ import annotations

import hashlib

from sage.world.lint import lint_room_candidate
from sage.world.package import load_world_package
from tests.fakes import ROOT

DEMO = load_world_package(ROOT / "worlds" / "demo")


def _room(room_type="room", direction="south", destination="start:commons"):
    return f"""id: start:pantry
zone: start
name: Pantry
type: {room_type}
description:
  base: Shelves of jars.
exits:
  {direction}:
    destination: {destination}
    description: Back out.
"""


def _tree_digest():
    base = ROOT / "worlds" / "demo" / "content" / "world"
    h = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if path.is_file():
            h.update(path.as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def test_a_room_that_fits_the_world_passes_and_nothing_is_written():
    before = _tree_digest()
    assert lint_room_candidate(DEMO, "start:pantry", _room()) == []
    assert _tree_digest() == before


def test_undeclared_type_and_direction_and_a_missing_destination_are_refused():
    assert lint_room_candidate(DEMO, "start:pantry", _room(room_type="dungeon")) == [
        "start:pantry: room type 'dungeon' is not in world.toml"
    ]
    assert lint_room_candidate(DEMO, "start:pantry", _room(direction="up")) == [
        "start:pantry: exit 'up' is not in world.toml"
    ]
    assert lint_room_candidate(DEMO, "start:pantry", _room(destination="start:cellar")) == [
        "start:pantry south: destination 'start:cellar' does not exist"
    ]
