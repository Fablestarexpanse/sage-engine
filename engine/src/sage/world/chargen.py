"""Character creation slots (contracts catalog #4): what a new character may choose.

A client sends world-defined ``chargen`` choices with character creation. ``chargen.validate``
turns them into a cleaned allocation or refuses with an error code; ``chargen.seed`` applies the
cleaned allocation to the new character's stats. With no provider, choices are ignored.

``chargen.options`` tells clients what to offer. The player client renders two kinds:

``"skill_points"``      ``title``, ``budget``, ``max_per_leaf``, ``domains``, ``leaves`` with
                        ``id``/``label``/``domain``; sent back as ``{"proficiencies": {leaf: level}}``.
``"attribute_points"``  ``title``, ``budget`` (the most all attributes may add up to),
                        ``attributes`` with ``key``/``label``/``short``/``min``/``max``/``default``;
                        sent back as ``{"attributes": {key: value}}``.

Options without a kind the client knows mean character creation has no choices step. A world
whose ``stats.yaml`` sets ``chargen.attribute_points`` gets ``attribute_points`` from the engine
without a plugin (``attribute_point_buy``); otherwise the default is ``{}``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

VALIDATE = "chargen.validate"
SEED = "chargen.seed"
OPTIONS = "chargen.options"


def default_validate(choices: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """(choices) -> (error code or None, cleaned). Default: nothing to choose."""
    return None, {}


def default_seed(stats: dict[str, Any], cleaned: dict[str, Any]) -> None:
    """(stats, cleaned): apply the allocation. Default: nothing."""
    return None


def default_options() -> dict[str, Any]:
    """() -> what a client may choose at creation (world-defined shape). Default: nothing."""
    return {}


def _whole(value: Any) -> int | None:
    """An integer choice, refusing bools, floats with a fraction and non-numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def attribute_point_buy(schema: Any, seed_attributes: Callable[[dict, dict], None]):
    """(validate, seed, options) for a stats.yaml with chargen.attribute_points.

    A character may set each attribute within its min..max, and all of them together may add up
    to at most the budget. Attributes left out keep their default.
    """
    from sage import lexicon

    budget = int(schema.chargen.attribute_points)
    attributes = {a.key: a for a in schema.attributes}

    def options() -> dict[str, Any]:
        return {
            "kind": "attribute_points",
            "title": lexicon.t("chargen.attributes.title"),
            "budget": budget,
            "attributes": [
                {
                    "key": a.key,
                    "label": lexicon.t(a.label),
                    "short": lexicon.t(a.short) if a.short else a.key.upper(),
                    "min": a.min,
                    "max": a.max,
                    "default": a.default,
                }
                for a in schema.attributes
            ],
        }

    def validate(choices: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        chosen = (choices or {}).get("attributes")
        if chosen is None:
            return None, {}
        if not isinstance(chosen, dict):
            return "invalid_attributes", {}
        spread = {key: a.default for key, a in attributes.items()}
        for key, raw in chosen.items():
            if key not in attributes:
                return f"unknown_attribute:{key}", {}
            value = _whole(raw)
            if value is None:
                return "invalid_attributes", {}
            if not attributes[key].min <= value <= attributes[key].max:
                return f"attribute_out_of_range:{key}", {}
            spread[key] = value
        if sum(spread.values()) > budget:
            return "attribute_budget_exceeded", {}
        return None, {"attributes": spread}

    def seed(stats: dict[str, Any], cleaned: dict[str, Any]) -> None:
        if cleaned.get("attributes"):
            seed_attributes(stats, dict(cleaned["attributes"]))

    return validate, seed, options
