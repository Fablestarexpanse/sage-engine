"""World package loading, validation and selection (contracts Part B)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from sage import ENGINE_VERSION
from sage.world.package import (
    WorldPackageError,
    available_worlds,
    load_world_package,
    select_world,
)

MANIFEST = """
[world]
id = "{id}"
name = "Test World"
version = "1.0.0"
engine = "{engine}"

[start]
room = "{room}"
respawn = "town:well"
"""


def make_world(
    root: Path,
    world_id: str = "demo",
    *,
    engine: str = ">=0.1",
    room: str = "town:gate",
    stats: str = "attributes:\n  - {key: brawn, label: stat.brawn.name, min: 1, max: 10, default: 3}\n",
    currencies: str = "- {key: coin, label: currency.coin.name, starting: 5}\n",
    make_content: bool = True,
) -> Path:
    world = root / world_id
    world.mkdir(parents=True)
    (world / "world.toml").write_text(
        MANIFEST.format(id=world_id, engine=engine, room=room), encoding="utf-8"
    )
    (world / "stats.yaml").write_text(stats, encoding="utf-8")
    (world / "currencies.yaml").write_text(currencies, encoding="utf-8")
    if make_content:
        (world / "content").mkdir()
    return world


def test_loads_a_valid_package(tmp_path):
    world = load_world_package(make_world(tmp_path))
    assert world.id == "demo"
    assert world.start_room == "town:gate"
    assert world.respawn_room == "town:well"
    assert [a.key for a in world.stats.attributes] == ["brawn"]
    assert [c.key for c in world.currencies] == ["coin"]
    assert world.content_dir == tmp_path.resolve() / "demo" / "content"


def test_transition_dirs_resolve_relative_to_the_package(tmp_path):
    shared = tmp_path / "shared_content"
    shared.mkdir()
    world_dir = make_world(tmp_path / "worlds", make_content=False)
    manifest = world_dir / "world.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + '\n[transition]\ncontent_dir = "../../shared_content"\n',
        encoding="utf-8",
    )
    assert load_world_package(world_dir).content_dir == shared.resolve()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"engine": ">=99"}, "needs engine"),
        ({"room": "no_colon"}, "zone_id:room_slug"),
        (
            {"stats": "attributes:\n  - {key: Bad Key, label: x, min: 1, max: 2, default: 1}\n"},
            "stat key",
        ),
        ({"make_content": False}, "content directory"),
    ],
)
def test_rejects_invalid_packages(tmp_path, kwargs, message):
    with pytest.raises(WorldPackageError, match=message):
        load_world_package(make_world(tmp_path, **kwargs))


def test_id_must_match_directory(tmp_path):
    world = make_world(tmp_path, "demo")
    renamed = world.rename(tmp_path / "other")
    with pytest.raises(WorldPackageError, match="must match its directory"):
        load_world_package(renamed)


def test_selection_rules(tmp_path):
    with pytest.raises(WorldPackageError, match="no world packages"):
        select_world(tmp_path, None)
    make_world(tmp_path, "alpha")
    assert select_world(tmp_path, None).id == "alpha"
    make_world(tmp_path, "beta")
    make_world(tmp_path, "_fixture")
    assert available_worlds(tmp_path) == ["alpha", "beta"]
    with pytest.raises(WorldPackageError, match="several worlds"):
        select_world(tmp_path, None)
    assert select_world(tmp_path, "beta").id == "beta"
    with pytest.raises(WorldPackageError, match="not found"):
        select_world(tmp_path, "gamma")


def test_engine_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert (
        tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"] == ENGINE_VERSION
    )


def test_repository_worlds_load():
    """Every world package committed to the repo loads on this engine."""
    worlds = Path(__file__).resolve().parents[2] / "worlds"
    ids = available_worlds(worlds)
    assert ids, "no world packages in worlds/"
    for world_id in ids:
        assert load_world_package(worlds / world_id).id == world_id
