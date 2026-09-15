"""`sage world new`: a package with one start room and no map, that loads, validates and boots."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from sage.cli import main
from sage.plugins.offline import registration_host
from sage.world.lint import lint_world
from sage.world.loader import ContentLoader
from sage.world.new import TEMPLATE, WorldNewError, create_world
from sage.world.package import load_world_package
from sage.world.schema import SCHEMA_FILE, content_schema, dumps
from tests.fakes import ROOT


@pytest.fixture()
def made(tmp_path):
    return create_world("my_town", tmp_path, ROOT, name="My Town")


def test_the_package_is_complete_and_validates(made):
    assert not made.errors and not made.warnings
    world = load_world_package(made.path)
    assert (world.id, world.manifest.world.name) == ("my_town", "My Town")
    assert world.manifest.start.room == "start:arrival"
    report = lint_world(world)
    assert (report.errors, report.warnings) == ([], [])
    assert list(report.rooms) == ["start:arrival"]  # one room, no map
    room = ContentLoader(world.content_dir).get_room("start:arrival")
    assert room is not None and room.exits == {}
    assert not (made.path / "content" / "world" / "zones" / "start" / ".positions.json").exists()
    for rel in ("README.md", "stats.yaml", "currencies.yaml", "lexicon/en.yaml", "ui/theme.yaml"):
        assert (made.path / rel).is_file(), rel
    assert "__WORLD" not in "".join(p.read_text(encoding="utf-8") for p in made.path.rglob("*.*"))


def test_the_manifest_pins_this_engine_and_lists_every_plugin_commented(made):
    from sage import ENGINE_VERSION

    text = (made.path / "world.toml").read_text(encoding="utf-8")
    manifest = tomllib.loads(text)
    major, minor = ENGINE_VERSION.split(".")[:2]
    assert manifest["world"]["engine"] == f">={major}.{minor},<{major}.{int(minor) + 1}"
    assert manifest.get("plugins", {}) == {}
    for plugin_dir in sorted((ROOT / "plugins").glob("*/plugin.toml")):
        plugin_id = tomllib.loads(plugin_dir.read_text(encoding="utf-8"))["plugin"]["id"]
        assert f'# {plugin_id} = "^' in text, plugin_id


def test_the_exported_schema_matches_the_engine_export(made):
    world = load_world_package(made.path)
    with registration_host(world, ROOT) as host:
        expected = dumps(content_schema(world, host.extensions))
    assert (made.path / SCHEMA_FILE).read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("bad", ["", "9town", "My_Town", "a", "x" * 33, "town-hall", "../up"])
def test_bad_ids_are_refused(tmp_path, bad):
    with pytest.raises(WorldNewError):
        create_world(bad, tmp_path, ROOT)
    assert list(tmp_path.iterdir()) == []


def test_an_existing_world_is_refused_and_force_keeps_other_files(made, tmp_path):
    with pytest.raises(WorldNewError):
        create_world("my_town", tmp_path, ROOT)
    extra = made.path / "content" / "world" / "zones" / "start" / "rooms" / "drawn.yaml"
    extra.write_text("id: start:drawn\n", encoding="utf-8")
    (made.path / "stats.yaml").write_text("changed", encoding="utf-8")
    again = create_world("my_town", tmp_path, ROOT, force=True)
    assert extra.read_text(encoding="utf-8") == "id: start:drawn\n"
    assert "attributes:" in (again.path / "stats.yaml").read_text(encoding="utf-8")


def test_the_template_names_no_world_or_setting(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "sage_invariants", ROOT / "scripts" / "sage_invariants.py"
    )
    inv = importlib.util.module_from_spec(spec)
    sys.modules["sage_invariants"] = inv
    spec.loader.exec_module(inv)
    denylist = inv.load_denylist(ROOT)
    hits = {
        p.relative_to(TEMPLATE).as_posix(): inv.find_terms(p.read_text(encoding="utf-8"), denylist)
        for p in TEMPLATE.rglob("*")
        if p.is_file()
    }
    assert {rel: found for rel, found in hits.items() if found} == {}


def test_db_commands_point_at_the_world_database(monkeypatch):
    from sage.cli import _use_world
    from sage.core.config import load_config

    for key in ("SAGE_SERVER__WORLD", "SAGE_DATABASE__DATABASE"):
        monkeypatch.setenv(key, "")  # records the original so _use_world's writes are undone
        monkeypatch.delenv(key)
    configured = load_config()
    _use_world("my_town")
    assert load_config().server.world == "my_town"
    expected = (
        configured.database.database if configured.server.world == "my_town" else "sage_my_town"
    )
    assert load_config().database.database == expected


def test_a_missing_database_is_recognised_through_wrappers():
    from sage.cli import _missing_database

    class InvalidCatalogNameError(Exception):
        pass

    try:
        try:
            raise InvalidCatalogNameError('database "sage_x" does not exist')
        except InvalidCatalogNameError as inner:
            raise RuntimeError("connect failed") from inner
    except RuntimeError as outer:
        assert _missing_database(outer)
    assert not _missing_database(RuntimeError("password authentication failed"))


def test_the_command_line(tmp_path, capsys):
    assert main(["world", "new", "harbor", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "harbor is ready" in out and "sage quickstart --world harbor" in out
    assert load_world_package(Path(tmp_path) / "harbor").manifest.world.name == "Harbor"
    assert main(["world", "new", "harbor", "--dir", str(tmp_path)]) == 1
