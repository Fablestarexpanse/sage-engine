"""
Effects engine — pure functions over a stats/state dict.

An effect instance is a plain dict stored under state["effects"], so player
effects ride the existing stats blob (PersistenceManager durability free) and
entity effects ride entity state in Redis. Shape:

    {
      "classification": "body.bleeding",   # dot-path identity, merge key
      "name": "bleeding",
      "description": "You are losing blood.",
      "kind": "dot" | "hot" | "flag",      # dot: damage/interval, hot: heal, flag: passive marker
      "magnitude": 2,                      # hp per tick for dot/hot; unused for flag
      "interval": 5.0,                     # seconds between ticks (dot/hot)
      "next_tick_at": 1700000000.0,        # absolute epoch seconds
      "expires_at": 1700000060.0 | None,   # None = indefinite
      "debuff": true,
      "survive_death": false,
    }

Absolute timestamps (epoch) mean effects survive a server restart intact.
Merge policy on re-application of the same classification: keep the stronger
magnitude and the later expiry (Epitaph's merge_effect + expected_tt pattern).
"""

import time
from typing import Any

EFFECTS_KEY = "effects"

KINDS = ("dot", "hot", "flag")


def ensure_effects(state: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(state.get(EFFECTS_KEY), list):
        state[EFFECTS_KEY] = []
    return state[EFFECTS_KEY]


def make_effect(
    classification: str,
    *,
    name: str,
    description: str = "",
    kind: str = "flag",
    magnitude: int = 0,
    interval: float = 5.0,
    duration: float | None = None,
    debuff: bool = True,
    survive_death: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    now = time.time() if now is None else now
    return {
        "classification": classification,
        "name": name,
        "description": description,
        "kind": kind,
        "magnitude": int(magnitude),
        "interval": float(interval),
        "next_tick_at": now + float(interval),
        "expires_at": None if duration is None else now + float(duration),
        "debuff": bool(debuff),
        "survive_death": bool(survive_death),
    }


def find_effects(state: dict[str, Any], classification: str) -> list[dict[str, Any]]:
    return [e for e in ensure_effects(state) if e.get("classification") == classification]


def apply_effect(state: dict[str, Any], effect: dict[str, Any]) -> bool:
    """
    Add an effect, merging with an existing one of the same classification.
    Returns True when the effect is new, False when it merged into an existing one.
    """
    effects = ensure_effects(state)
    for existing in effects:
        if existing.get("classification") == effect.get("classification"):
            existing["magnitude"] = max(
                int(existing.get("magnitude", 0)), int(effect.get("magnitude", 0))
            )
            old_exp = existing.get("expires_at")
            new_exp = effect.get("expires_at")
            if old_exp is None or new_exp is None:
                existing["expires_at"] = None
            else:
                existing["expires_at"] = max(old_exp, new_exp)
            return False
    effects.append(dict(effect))
    return True


def remove_effects(state: dict[str, Any], classification: str) -> int:
    """Delete every instance of a classification (Epitaph: always delete all). Returns count."""
    effects = ensure_effects(state)
    kept = [e for e in effects if e.get("classification") != classification]
    removed = len(effects) - len(kept)
    state[EFFECTS_KEY] = kept
    return removed


def clear_on_death(state: dict[str, Any]) -> None:
    """Drop everything that doesn't declare survive_death."""
    state[EFFECTS_KEY] = [e for e in ensure_effects(state) if e.get("survive_death")]


def process_effects(state: dict[str, Any], now: float | None = None) -> list[str]:
    """
    Advance due dot/hot ticks and drop expired effects. Mutates state["hp"]
    (floored at 0, capped at max_hp for heals) and returns player-facing
    messages in the order things happened.
    """
    now = time.time() if now is None else now
    effects = ensure_effects(state)
    messages: list[str] = []
    surviving: list[dict[str, Any]] = []

    for eff in effects:
        expired = eff.get("expires_at") is not None and now >= eff["expires_at"]
        # Fire any ticks that came due before expiry.
        while eff.get("kind") in ("dot", "hot") and eff.get("next_tick_at", now) <= now:
            tick_at = eff["next_tick_at"]
            if eff.get("expires_at") is not None and tick_at > eff["expires_at"]:
                break
            magnitude = int(eff.get("magnitude", 0))
            if eff["kind"] == "dot" and magnitude > 0:
                state["hp"] = max(0, int(state.get("hp", 0)) - magnitude)
                messages.append(f"{eff.get('description') or eff.get('name')} (-{magnitude} hp)")
            elif eff["kind"] == "hot" and magnitude > 0:
                max_hp = int(state.get("max_hp", state.get("hp", 0)))
                state["hp"] = min(max_hp, int(state.get("hp", 0)) + magnitude)
                messages.append(f"{eff.get('description') or eff.get('name')} (+{magnitude} hp)")
            eff["next_tick_at"] = tick_at + float(eff.get("interval", 5.0))
        if expired:
            messages.append(f"The {eff.get('name', 'effect')} subsides.")
        else:
            surviving.append(eff)

    state[EFFECTS_KEY] = surviving
    return messages


def describe_effects(state: dict[str, Any], now: float | None = None) -> list[str]:
    """Lines for the 'effects' command: name, description, remaining time."""
    now = time.time() if now is None else now
    lines = []
    for eff in ensure_effects(state):
        tag = "debuff" if eff.get("debuff", True) else "buff"
        expires = eff.get("expires_at")
        remain = "indefinite" if expires is None else f"{max(0, int(expires - now))}s left"
        desc = eff.get("description") or ""
        lines.append(f"  [{tag}] {eff.get('name', '?')} — {desc} ({remain})".rstrip())
    return lines
