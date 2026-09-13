"""Search/scavenge: model validation, chance math, sample content integrity."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fablestar.commands.search import CHANCE_CAP, find_chance
from fablestar.world.models import FeatureModel, RoomModel, SearchModel


def test_search_model_defaults():
    s = SearchModel(items=["ration_pack"])
    assert s.max_finds == 1
    assert s.respawn_s == 600.0
    assert s.chance == 0.7


def test_search_model_requires_items():
    with pytest.raises(ValidationError):
        SearchModel(items=[])


def test_feature_search_defaults_to_none():
    f = FeatureModel(id="x", name="x", keywords=["x"], description="d")
    assert f.search is None


def test_room_parses_feature_with_search_block():
    room = RoomModel(
        id="z:r",
        zone="z",
        type="hub",
        features=[
            {
                "id": "crates",
                "name": "crates",
                "keywords": ["crates"],
                "description": "d",
                "search": {"items": ["ration_pack"], "max_finds": 2},
            }
        ],
    )
    assert room.features[0].search is not None
    assert room.features[0].search.max_finds == 2


def test_find_chance_scales_with_perception_and_caps():
    assert find_chance(0.6, 0) == 0.6
    assert find_chance(0.6, 20) == pytest.approx(0.7)
    assert find_chance(0.6, 1000) == CHANCE_CAP


def test_find_chance_negative_level_ignored():
    assert find_chance(0.5, -50) == 0.5


def test_world_search_profiles_reference_real_items():
    """Every search profile in every shipped zone points at a real item."""
    room_files = sorted(Path("content/world/zones").glob("*/rooms/*.yaml"))
    assert room_files, "no world rooms found"
    searchable_count = 0
    for rf in room_files:
        room = RoomModel(**yaml.safe_load(rf.read_text(encoding="utf-8")))
        for f in room.features:
            if not f.search:
                continue
            searchable_count += 1
            for item_id in f.search.items:
                path = Path("content/world/items") / f"{item_id}.yaml"
                assert path.exists(), f"{rf.name}: search references missing item {item_id}"
    assert searchable_count, "world should ship at least one searchable feature"
