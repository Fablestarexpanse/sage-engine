"""Content Library detail: template saves are validated; a room's file is readable with its findings."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sage.admin import content_browser
from tests.fakes import ROOT


@pytest.fixture()
def demo_copy(tmp_path: Path):
    shutil.copytree(ROOT / "worlds" / "demo" / "content", tmp_path / "content")
    previous = content_browser.CONTENT_WORLD.parent
    content_browser.set_content_root(tmp_path / "content")
    try:
        yield tmp_path / "content" / "world"
    finally:
        content_browser.set_content_root(previous)


def test_a_valid_item_template_is_saved(demo_copy):
    path = content_browser.save_template_yaml_text(
        "items", "apple", "id: apple\nname: apple\ntype: consumable\nvalue: 1\n"
    )
    assert path == demo_copy / "items" / "apple.yaml" and path.is_file()


@pytest.mark.parametrize(
    "text, reason",
    [
        ("id: apple\nname: [unclosed\n", "invalid_yaml"),
        ("- just\n- a list\n", "invalid_yaml: top level must be a mapping"),
        ("id: apple\ntype: consumable\n", "invalid_template: name: Field required"),
        ("id: pear\nname: pear\n", "id_mismatch: expected apple, got pear"),
    ],
)
def test_a_template_the_loader_cannot_use_is_refused_and_not_written(demo_copy, text, reason):
    with pytest.raises(ValueError) as caught:
        content_browser.save_template_yaml_text("items", "apple", text)
    assert str(caught.value).startswith(reason)
    assert not (demo_copy / "items" / "apple.yaml").exists()


def test_room_detail_returns_the_file_and_its_fields(demo_copy):
    detail = content_browser.room_detail("start", "commons")
    assert detail["id"] == "start:commons"
    assert detail["data"]["name"] == "The Commons"
    assert set(detail["data"]["exits"]) == {"north", "east", "west"}
    assert "base:" in detail["yaml"] and detail["parse_error"] is None
    assert content_browser.room_detail("start", "nowhere") is None
    with pytest.raises(ValueError):
        content_browser.room_detail("start", "../commons")


def test_overview_counts_every_entity_template_on_disk(demo_copy):
    (demo_copy / "entities").mkdir(exist_ok=True)
    (demo_copy / "entities" / "moth.yaml").write_text("id: moth\nname: moth\n", encoding="utf-8")
    assert content_browser.content_overview()["entity_templates"] == 1
    assert [r["id"] for r in content_browser.list_entity_template_rows()] == ["moth"]


def _write(folder: Path, name: str, text: str) -> Path:
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


PLUGIN_FIELDS = {
    "item.attack": {"owner": "combat", "schema": {"title": "Bonus", "type": "integer"}},
    "item.recipe": {"owner": "crafting", "schema": {"type": "object"}},
    "room.shop": {"owner": "shop", "schema": {"type": "object"}},
}


def test_item_table_columns_come_from_the_model_and_plugin_fields(demo_copy):
    from sage.admin import content_tables

    items = demo_copy / "items"
    _write(
        items, "blade", "id: blade\nname: Blade\ntype: weapon\nvalue: 9\nattack: 4\ntags: [sharp]\n"
    )
    _write(
        items,
        "club",
        "id: club\nname: Club\ntype: weapon\nvalue: 2\nattack: 2\nrecipe: {wood: 2}\n",
    )
    _write(items, "bread", "id: bread\nname: Bread\ntype: food\nvalue: 1\n")
    _write(items, "broken", "id: broken\nname: [unclosed\n")

    table = content_tables.table("items", PLUGIN_FIELDS, sort="attack", desc=True)
    keys = [c["key"] for c in table["columns"]]
    assert keys[0] == "type" and {"value", "attack", "recipe"} <= set(keys) and "shop" not in keys
    assert [c["owner"] for c in table["columns"] if c["key"] == "attack"] == ["combat"]
    # Highest attack first; rows without a value and the file that does not parse come last.
    assert [r["id"] for r in table["rows"]][:2] == ["blade", "club"]
    assert table["total"] == 4 and table["types"] == ["food", "weapon"]
    broken = next(r for r in table["rows"] if r["id"] == "broken")
    assert broken["parse_error"] and broken["values"] == {}
    club = next(r for r in table["rows"] if r["id"] == "club")
    assert club["values"]["recipe"] == 1

    assert [r["id"] for r in content_tables.table("items", PLUGIN_FIELDS, q="sharp")["rows"]] == [
        "blade"
    ]
    weapons = content_tables.table("items", PLUGIN_FIELDS, type_="weapon", limit=1, offset=1)
    assert (weapons["total"], [r["id"] for r in weapons["rows"]]) == (2, ["club"])


def test_creature_stats_become_columns(demo_copy):
    from sage.admin import content_tables

    folder = demo_copy / "entities"
    _write(folder, "moth", "id: moth\nname: moth\nstats: {hp: 3}\n")
    _write(
        folder,
        "wolf",
        "id: wolf\nname: wolf\nstats: {hp: 20, attack: 5}\nloot: [{template: pelt}]\n",
    )
    table = content_tables.table("entities", {}, sort="stats.hp", desc=True)
    assert {"stats.hp", "stats.attack", "loot"} <= {c["key"] for c in table["columns"]}
    assert [(r["id"], r["values"]["stats.hp"]) for r in table["rows"]] == [
        ("wolf", 20),
        ("moth", 3),
    ]


def test_a_changed_file_is_parsed_again(demo_copy):
    import os

    path = _write(demo_copy / "items", "apple", "id: apple\nname: apple\n")
    assert content_browser.load_yaml(path)[0]["name"] == "apple"
    path.write_text("id: apple\nname: green apple\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert content_browser.load_yaml(path)[0]["name"] == "green apple"
