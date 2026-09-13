"""Effects engine: apply/merge, ticking, expiry, death filter, hazard application."""

import random

from sage.effects.engine import (
    EFFECTS_KEY,
    apply_effect,
    clear_on_death,
    describe_effects,
    find_effects,
    make_effect,
    process_effects,
    remove_effects,
)
from sage.effects.hazards import apply_room_hazards
from sage.proficiencies.state_helpers import CONDUIT_KEY
from sage.world.models import RoomModel

T0 = 1_000_000.0


def _dot(magnitude=2, interval=5.0, duration=20.0, **kw):
    return make_effect(
        "body.bleeding",
        name="bleeding",
        description="You are losing blood.",
        kind="dot",
        magnitude=magnitude,
        interval=interval,
        duration=duration,
        now=T0,
        **kw,
    )


def test_apply_new_effect():
    state = {"hp": 20}
    assert apply_effect(state, _dot()) is True
    assert len(find_effects(state, "body.bleeding")) == 1


def test_merge_keeps_stronger_magnitude_and_later_expiry():
    state = {"hp": 20}
    apply_effect(state, _dot(magnitude=5, duration=10.0))
    assert apply_effect(state, _dot(magnitude=2, duration=60.0)) is False
    (eff,) = find_effects(state, "body.bleeding")
    assert eff["magnitude"] == 5
    assert eff["expires_at"] == T0 + 60.0


def test_merge_indefinite_wins():
    state = {"hp": 20}
    apply_effect(state, _dot(duration=10.0))
    apply_effect(state, make_effect("body.bleeding", name="b", kind="dot", now=T0))
    (eff,) = find_effects(state, "body.bleeding")
    assert eff["expires_at"] is None


def test_dot_ticks_damage_and_reschedules():
    state = {"hp": 20}
    apply_effect(state, _dot(magnitude=3, interval=5.0, duration=60.0))
    msgs = process_effects(state, now=T0 + 11.0)  # ticks due at T0+5 and T0+10
    assert state["hp"] == 14
    assert len(msgs) == 2
    (eff,) = find_effects(state, "body.bleeding")
    assert eff["next_tick_at"] == T0 + 15.0


def test_hot_heals_capped_at_max_hp():
    state = {"hp": 18, "max_hp": 20}
    heal = make_effect(
        "body.mending", name="mending", kind="hot", magnitude=5, interval=5.0, now=T0, debuff=False
    )
    apply_effect(state, heal)
    process_effects(state, now=T0 + 5.0)
    assert state["hp"] == 20


def test_dot_never_drops_hp_below_zero():
    state = {"hp": 2}
    apply_effect(state, _dot(magnitude=10))
    process_effects(state, now=T0 + 5.0)
    assert state["hp"] == 0


def test_expired_effect_removed_with_message():
    state = {"hp": 20}
    apply_effect(state, _dot(duration=4.0))  # expires before first tick at +5
    msgs = process_effects(state, now=T0 + 4.5)
    assert state[EFFECTS_KEY] == []
    assert any("subsides" in m for m in msgs)


def test_remove_effects_deletes_all_instances():
    state = {"hp": 20}
    apply_effect(state, _dot())
    assert remove_effects(state, "body.bleeding") == 1
    assert state[EFFECTS_KEY] == []


def test_clear_on_death_respects_survive_death():
    state = {"hp": 0}
    apply_effect(state, _dot())
    keeper = make_effect("story.marked", name="marked", kind="flag", survive_death=True, now=T0)
    apply_effect(state, keeper)
    clear_on_death(state)
    assert [e["classification"] for e in state[EFFECTS_KEY]] == ["story.marked"]


def test_describe_effects_lines():
    state = {"hp": 20}
    apply_effect(state, _dot(duration=30.0))
    (line,) = describe_effects(state, now=T0)
    assert "[debuff] bleeding" in line
    assert "30s left" in line


def _hazard_room(severity=2):
    return RoomModel(
        id="z:r",
        zone="z",
        type="chamber",
        hazards=[
            {
                "id": "vent",
                "type": "radiation",
                "severity": severity,
                "description": "Radiation prickles across your skin.",
            }
        ],
    )


def test_hazard_applies_dot_scaled_by_severity():
    state = {"hp": 20}
    msgs = apply_room_hazards(state, _hazard_room(severity=3), rng=random.Random(1), now=T0)
    (eff,) = find_effects(state, "hazard.radiation")
    assert eff["magnitude"] == 3
    assert eff["expires_at"] == T0 + 30.0  # 6 * (2 + 3)
    assert any("takes hold" in m for m in msgs)


def test_hazard_resist_skips_application():
    state = {
        "hp": 20,
        CONDUIT_KEY: {"proficiencies": {"traversal.survival.hazard_resist": {"level": 100}}},
    }
    rng = random.Random(1)  # first random() ≈ 0.134 < 0.75 resist cap → resisted
    msgs = apply_room_hazards(state, _hazard_room(), rng=rng, now=T0)
    assert find_effects(state, "hazard.radiation") == []
    assert any("shrug it off" in m for m in msgs)


def test_room_without_hazards_is_noop():
    state = {"hp": 20}
    room = RoomModel(id="z:r", zone="z", type="chamber")
    assert apply_room_hazards(state, room, rng=random.Random(1), now=T0) == []
    assert state.get(EFFECTS_KEY) in (None, [])
