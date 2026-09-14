"""Admin World Builder writes to .positions.json must not destroy WorldForge metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sage.admin import content_browser


@pytest.fixture
def zone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    zones = tmp_path / "zones"
    (zones / "isle" / "rooms").mkdir(parents=True)
    monkeypatch.setattr(content_browser, "ZONES_ROOT", zones)
    doc = {
        "version": 2,
        "positions": {"dock": {"x": 1, "y": 2}, "tower": {"x": 3, "y": 4}},
        "notes": [{"id": "n1"}],
        "muted_edges": [],
        "floors": {"dock": 0, "tower": 1},
        "future_key": {"kept": True},
    }
    (zones / "isle" / ".positions.json").write_text(json.dumps(doc), encoding="utf-8")
    return zones / "isle" / ".positions.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_save_positions_keeps_floors_and_unknown_keys(zone: Path) -> None:
    content_browser.save_zone_positions(
        "isle", {"dock": {"x": 10, "y": 20}, "tower": {"x": 30, "y": 40}}
    )
    doc = _read(zone)
    assert doc["positions"]["dock"] == {"x": 10.0, "y": 20.0}
    assert doc["floors"] == {"dock": 0, "tower": 1}
    assert doc["future_key"] == {"kept": True}
    assert doc["notes"] == [{"id": "n1"}]


def test_delete_room_keeps_floors_of_remaining_rooms(zone: Path) -> None:
    rooms = zone.parent / "rooms"
    (rooms / "tower.yaml").write_text("id: isle:tower\n", encoding="utf-8")
    content_browser.delete_room("isle", "tower")
    doc = _read(zone)
    assert "tower" not in doc["positions"]
    assert doc["floors"]["dock"] == 0
