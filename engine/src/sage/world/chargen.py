"""Character creation slots (contracts catalog #4): what a new character may choose.

A client sends world-defined ``chargen`` choices with character creation. ``chargen.validate``
turns them into a cleaned allocation or refuses with an error code; ``chargen.seed`` applies the
cleaned allocation to the new character's stats. With no provider, choices are ignored.
"""

from __future__ import annotations

from typing import Any

VALIDATE = "chargen.validate"
SEED = "chargen.seed"


def default_validate(choices: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """(choices) -> (error code or None, cleaned). Default: nothing to choose."""
    return None, {}


def default_seed(stats: dict[str, Any], cleaned: dict[str, Any]) -> None:
    """(stats, cleaned): apply the allocation. Default: nothing."""
    return None
