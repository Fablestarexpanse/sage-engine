"""
Agent Feelings — deterministic mood/needs/bonds in the stats blob.

The LLM never decides how an agent feels; rules move the state and the brain
is told about it. Everything decays toward the persona baseline so agents
return to themselves. All pure functions for testability.
"""

from typing import Any

from fablestar.agents.models import AgentPersonaModel

FEELINGS_KEY = "feelings"
DECAY_RATE = 0.03  # per feelings tick (~2s): fraction of distance to baseline
NEED_RISE = {
    "rest": 0.002,
    "company": 0.004,
    "purpose": 0.003,
    "safety": 0.0,
    # ~0.0012/2s → hungry (0.7) in about 20 minutes of play.
    "hunger": 0.0012,
}


def ensure_feelings(stats: dict[str, Any], persona: AgentPersonaModel) -> dict[str, Any]:
    f = stats.get(FEELINGS_KEY)
    if not isinstance(f, dict) or "mood" not in f:
        f = {
            "mood": {
                "valence": persona.baseline_mood.valence,
                "arousal": persona.baseline_mood.arousal,
            },
            "needs": {"rest": 0.2, "company": 0.3, "purpose": 0.4, "safety": 0.1, "hunger": 0.2},
            "bonds": {},
        }
        stats[FEELINGS_KEY] = f
    return f


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _nudge(f: dict[str, Any], valence: float = 0.0, arousal: float = 0.0, **needs: float):
    f["mood"]["valence"] = _clamp(f["mood"]["valence"] + valence, -1.0, 1.0)
    f["mood"]["arousal"] = _clamp(f["mood"]["arousal"] + arousal, 0.0, 1.0)
    for need, delta in needs.items():
        f["needs"][need] = _clamp(f["needs"].get(need, 0.0) + delta, 0.0, 1.0)


# Event rules — each returns True when it changed anything (for dirty tracking).


def on_hurt(stats: dict[str, Any], persona: AgentPersonaModel, fraction_lost: float) -> None:
    f = ensure_feelings(stats, persona)
    _nudge(f, valence=-0.15 - 0.3 * fraction_lost, arousal=0.25, safety=0.3, rest=0.1)


def on_kill(stats: dict[str, Any], persona: AgentPersonaModel) -> None:
    f = ensure_feelings(stats, persona)
    _nudge(f, valence=0.05, arousal=0.1, purpose=-0.2, safety=-0.1)


def on_company(stats: dict[str, Any], persona: AgentPersonaModel, other: str) -> None:
    f = ensure_feelings(stats, persona)
    warmth = persona.temperament.warmth
    _nudge(f, valence=0.05 * warmth, company=-0.15 * (0.5 + warmth))
    bond = f["bonds"].setdefault(other, {"affinity": 0.0, "tags": []})
    bond["affinity"] = _clamp(bond["affinity"] + 0.02 * warmth, -1.0, 1.0)


def on_goal_done(stats: dict[str, Any], persona: AgentPersonaModel) -> None:
    f = ensure_feelings(stats, persona)
    _nudge(f, valence=0.1, purpose=-0.3)


def on_rested(stats: dict[str, Any], persona: AgentPersonaModel) -> None:
    f = ensure_feelings(stats, persona)
    _nudge(f, rest=-0.5, arousal=-0.1)


def on_ate(stats: dict[str, Any], persona: AgentPersonaModel) -> None:
    f = ensure_feelings(stats, persona)
    _nudge(f, valence=0.05, hunger=-0.6)


def on_slept_home(stats: dict[str, Any], persona: AgentPersonaModel) -> None:
    """Sleeping in your own rented room beats a bench in the clinic."""
    f = ensure_feelings(stats, persona)
    _nudge(f, valence=0.1, rest=-0.8, safety=-0.4, arousal=-0.15)


def decay_tick(stats: dict[str, Any], persona: AgentPersonaModel) -> None:
    """Mood drifts toward baseline; needs rise slowly with time."""
    f = ensure_feelings(stats, persona)
    mood = f["mood"]
    mood["valence"] += (persona.baseline_mood.valence - mood["valence"]) * DECAY_RATE
    mood["arousal"] += (persona.baseline_mood.arousal - mood["arousal"]) * DECAY_RATE
    for need, rate in NEED_RISE.items():
        f["needs"][need] = _clamp(f["needs"].get(need, 0.0) + rate, 0.0, 1.0)


MEMORY_KEY = "agent_memories"
MEMORY_CAP = 40


def remember(stats: dict[str, Any], text: str) -> None:
    """Append one notable event to the agent's memory ring (stats blob = durable)."""
    ring = stats.get(MEMORY_KEY)
    if not isinstance(ring, list):
        ring = []
        stats[MEMORY_KEY] = ring
    ring.append(text[:200])
    del ring[:-MEMORY_CAP]


def recall(stats: dict[str, Any], n: int = 10) -> list[str]:
    ring = stats.get(MEMORY_KEY)
    return list(ring[-n:]) if isinstance(ring, list) else []


def mood_word(stats: dict[str, Any], persona: AgentPersonaModel) -> str:
    """One human word for the admin table and brain prompts."""
    f = ensure_feelings(stats, persona)
    v, a = f["mood"]["valence"], f["mood"]["arousal"]
    if v > 0.35:
        return "elated" if a > 0.55 else "content"
    if v < -0.35:
        return "distressed" if a > 0.55 else "despondent"
    return "agitated" if a > 0.65 else "steady"
