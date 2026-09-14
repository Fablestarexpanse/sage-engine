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
