"""Factions: standing math, kill reputation, registry loading."""

from pathlib import Path

from fablestar.factions.engine import (
    FACTIONS_KEY,
    adjust_rep,
    apply_kill_reputation,
    get_rep,
    standings_lines,
)
from fablestar.factions.models import REP_MAX, REP_MIN, FactionModel, standing_name
from fablestar.factions.registry import FactionRegistry, load_factions


def _faction(**overrides) -> FactionModel:
    base = {"id": "union", "name": "Salvage Union", "description": "d"}
    base.update(overrides)
    return FactionModel(**base)


def test_standing_names_cover_range():
    assert standing_name(-150) == "loathed"
    assert standing_name(-60) == "disliked"  # boundary: -60 is not < -60
    assert standing_name(0) == "neutral"
    assert standing_name(30) == "liked"
    assert standing_name(150) == "exalted"


def test_initial_rep_used_until_first_change():
    f = _faction(initial_rep=25)
    stats: dict = {}
    assert get_rep(stats, f) == 25
    adjust_rep(stats, f, -5)
    assert get_rep(stats, f) == 20
    assert stats[FACTIONS_KEY]["union"] == 20


def test_adjust_rep_announces_only_level_crossings():
    f = _faction()
    stats: dict = {}
    assert adjust_rep(stats, f, 5) is None  # 0 -> 5, still neutral
    msg = adjust_rep(stats, f, 20)  # 5 -> 25, neutral -> liked
    assert msg is not None and "improves" in msg and "liked" in msg
    msg = adjust_rep(stats, f, -50)  # 25 -> -25, liked -> disliked
    assert msg is not None and "worsens" in msg and "disliked" in msg


def test_rep_clamped_to_bounds():
    f = _faction()
    stats: dict = {}
    adjust_rep(stats, f, -10_000)
    assert get_rep(stats, f) == REP_MIN
    adjust_rep(stats, f, 10_000)
    assert get_rep(stats, f) == REP_MAX


def test_kill_reputation_penalises_own_faction_and_rewards_enemies():
    union = _faction(id="union", name="Union", kill_rep=-30)
    guild = _faction(id="guild", name="Guild", enemies=["scrap_drone"], enemy_kill_rep=25)
    reg = FactionRegistry([union, guild])
    stats: dict = {}
    messages = apply_kill_reputation(stats, reg, "scrap_drone", "union")
    assert stats[FACTIONS_KEY]["union"] == -30
    assert stats[FACTIONS_KEY]["guild"] == 25
    assert len(messages) == 2  # both crossed a standing level


def test_kill_reputation_unknown_faction_noop():
    reg = FactionRegistry([])
    stats: dict = {}
    assert apply_kill_reputation(stats, reg, "scrap_drone", "ghost_faction") == []
    assert stats.get(FACTIONS_KEY) in (None, {})


def test_standings_lines_include_every_faction():
    reg = FactionRegistry([_faction(), _faction(id="g", name="Guild")])
    lines = standings_lines({}, reg)
    assert len(lines) == 2
    assert any("Salvage Union" in line and "neutral" in line for line in lines)


def test_repo_content_factions_load():
    reg = load_factions(Path("content"))
    ids = {f.id for f in reg.all()}
    assert {"salvage_union", "dockworkers"} <= ids
    assert reg.enemies_of_template("scrap_drone")[0].id == "dockworkers"
