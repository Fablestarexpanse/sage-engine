"""Achievement registry loading + engine grant logic."""

from pathlib import Path

from fablestar.achievements.engine import (
    COUNTERS_KEY,
    GRANTS_KEY,
    announcement,
    record_counter,
    record_room_visit,
)
from fablestar.achievements.models import AchievementModel
from fablestar.achievements.registry import AchievementRegistry, load_achievements


def _registry(*achievements: AchievementModel) -> AchievementRegistry:
    return AchievementRegistry(list(achievements))


def _ach(**overrides) -> AchievementModel:
    base = {
        "id": "ten_kills",
        "name": "Ten Kills",
        "story": "killed ten things",
        "level": "minor",
        "criteria": {"kills": 10},
    }
    base.update(overrides)
    return AchievementModel(**base)


def test_record_counter_grants_at_threshold():
    reg = _registry(_ach(criteria={"kills": 2}))
    stats: dict = {}
    assert record_counter(stats, reg, "kills") == []
    granted = record_counter(stats, reg, "kills")
    assert [a.id for a in granted] == ["ten_kills"]
    assert stats[COUNTERS_KEY]["kills"] == 2
    assert "granted_at" in stats[GRANTS_KEY]["ten_kills"]


def test_no_double_grant():
    reg = _registry(_ach(criteria={"kills": 1}))
    stats: dict = {}
    assert len(record_counter(stats, reg, "kills")) == 1
    assert record_counter(stats, reg, "kills") == []
    assert stats[COUNTERS_KEY]["kills"] == 2


def test_match_all_requires_every_counter():
    reg = _registry(_ach(criteria={"kills": 1, "rooms_visited": 2}))
    stats: dict = {}
    assert record_counter(stats, reg, "kills") == []
    record_counter(stats, reg, "rooms_visited")
    granted = record_counter(stats, reg, "rooms_visited")
    assert [a.id for a in granted] == ["ten_kills"]


def test_match_any_grants_on_first_met():
    reg = _registry(_ach(criteria={"kills": 5, "rooms_visited": 1}, match="any"))
    stats: dict = {}
    granted = record_counter(stats, reg, "rooms_visited")
    assert [a.id for a in granted] == ["ten_kills"]


def test_room_visit_counts_unique_rooms_only():
    reg = _registry(_ach(id="walker", criteria={"rooms_visited": 2}))
    stats: dict = {}
    assert record_room_visit(stats, reg, "z:a") == []
    assert record_room_visit(stats, reg, "z:a") == []
    granted = record_room_visit(stats, reg, "z:b")
    assert [a.id for a in granted] == ["walker"]
    assert stats[COUNTERS_KEY]["rooms_visited"] == 2


def test_unrelated_counter_does_not_trigger_check():
    reg = _registry(_ach(criteria={"kills": 1}))
    stats: dict = {}
    assert record_counter(stats, reg, "crafts") == []
    assert stats[GRANTS_KEY] == {}


def test_announcement_format():
    line = announcement(_ach())
    assert "Ten Kills, in which you killed ten things" in line
    assert "minor" in line


def test_load_achievements_from_disk(tmp_path: Path):
    d = tmp_path / "achievements"
    d.mkdir()
    (d / "one.yaml").write_text(
        "name: One\nstory: did a thing\ncriteria:\n  kills: 1\n", encoding="utf-8"
    )
    (d / "broken.yaml").write_text("name: [unclosed", encoding="utf-8")
    (d / "bad_level.yaml").write_text(
        "name: Bad\nstory: nope\nlevel: colossal\ncriteria:\n  kills: 1\n", encoding="utf-8"
    )
    reg = load_achievements(tmp_path)
    ids = [a.id for a in reg.all()]
    assert ids == ["one"]  # id defaults to file stem; invalid files skipped
    assert reg.watching("kills")[0].id == "one"


def test_load_achievements_missing_dir(tmp_path: Path):
    reg = load_achievements(tmp_path)
    assert reg.all() == []


def test_repo_content_achievements_load():
    reg = load_achievements(Path("content"))
    ids = {a.id for a in reg.all()}
    assert {"first_blood", "exterminator", "pathfinder"} <= ids
