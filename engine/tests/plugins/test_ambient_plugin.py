"""Ambient room-chat model and scheduling helpers."""

import random

import pytest
from pydantic import ValidationError
from sage_plugin_ambient.main import AmbientModel, next_due, pick_line


def _ambient(**overrides) -> AmbientModel:
    base = {"lines": ["a", "b", "c"], "min_interval": 10, "max_interval": 20}
    base.update(overrides)
    return AmbientModel(**base)


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


def test_empty_lines_refused():
    with pytest.raises(ValidationError):
        AmbientModel(lines=[])


ROOM = """id: town:square
zone: town
type: hub
ambient: {lines: ["A bell rings."], min_interval: 1, max_interval: 1}
"""


def test_occupied_rooms_get_lines_and_leavers_do_not_crash(plugin_host, tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from sage_plugin_ambient.main import AmbientDirector

    from tests.fakes import StubSession, repo_world

    rooms = tmp_path / "content" / "world" / "zones" / "town" / "rooms"
    rooms.mkdir(parents=True)
    (rooms / "square.yaml").write_text(ROOM, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    content_override = tmp_path / "content"
    session = StubSession("hero")
    server = SimpleNamespace(
        session_manager=SimpleNamespace(
            player_to_session={"hero": "s1", "gone": "s2"},
            get_session_by_player=lambda pid: session if pid == "hero" else None,
        )
    )
    host = plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies, content_override),
        ["ambient"],
        server=server,
    )
    host.redis.locations["hero"] = "town:square"
    api = next(r.api for r in host.loaded if r.id == "ambient")
    director = AmbientDirector(api, rng=random.Random(1))
    clock = [100.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    asyncio.run(director.on_check(0))  # first sighting schedules
    clock[0] += 5
    asyncio.run(director.on_check(1))
    assert session.sent == ["A bell rings."]
