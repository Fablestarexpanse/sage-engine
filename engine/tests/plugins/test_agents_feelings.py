"""Agent feelings: event rules, decay toward baseline, mood words."""

from sage_plugin_agents.feelings import (
    decay_tick,
    ensure_feelings,
    mood_word,
    on_company,
    on_goal_done,
    on_hurt,
)
from sage_plugin_agents.models import AgentPersonaModel


def _persona(**overrides) -> AgentPersonaModel:
    base = {
        "id": "sela",
        "name": "Sela",
        "spawn_room": "z:r",
        "baseline_mood": {"valence": 0.2, "arousal": 0.4},
        "temperament": {"warmth": 0.8},
    }
    base.update(overrides)
    return AgentPersonaModel(**base)


def test_ensure_seeds_from_baseline():
    p = _persona()
    stats: dict = {}
    f = ensure_feelings(stats, p)
    assert f["mood"]["valence"] == 0.2
    assert 0 <= f["needs"]["company"] <= 1


def test_hurt_drops_valence_spikes_arousal_and_safety():
    p = _persona()
    stats: dict = {}
    f = ensure_feelings(stats, p)
    before = dict(f["mood"])
    on_hurt(stats, p, fraction_lost=0.3)
    assert f["mood"]["valence"] < before["valence"]
    assert f["mood"]["arousal"] > before["arousal"]
    assert f["needs"]["safety"] > 0.1


def test_company_warms_and_builds_bond():
    p = _persona()
    stats: dict = {}
    on_company(stats, p, "Testa Runn")
    on_company(stats, p, "Testa Runn")
    f = stats["feelings"]
    assert f["bonds"]["Testa Runn"]["affinity"] > 0
    assert f["needs"]["company"] < 0.3


def test_goal_done_satisfies_purpose():
    p = _persona()
    stats: dict = {}
    ensure_feelings(stats, p)
    on_goal_done(stats, p)
    assert stats["feelings"]["needs"]["purpose"] < 0.4


def test_decay_returns_mood_toward_baseline():
    p = _persona()
    stats: dict = {}
    on_hurt(stats, p, fraction_lost=0.5)
    hurt_valence = stats["feelings"]["mood"]["valence"]
    for _ in range(200):
        decay_tick(stats, p)
    assert stats["feelings"]["mood"]["valence"] > hurt_valence
    assert abs(stats["feelings"]["mood"]["valence"] - 0.2) < 0.1


def test_mood_words_cover_quadrants():
    p = _persona()
    stats: dict = {"feelings": {"mood": {"valence": 0.5, "arousal": 0.8}, "needs": {}, "bonds": {}}}
    assert mood_word(stats, p) == "elated"
    stats["feelings"]["mood"] = {"valence": -0.5, "arousal": 0.2}
    assert mood_word(stats, p) == "despondent"
    stats["feelings"]["mood"] = {"valence": 0.0, "arousal": 0.3}
    assert mood_word(stats, p) == "steady"
