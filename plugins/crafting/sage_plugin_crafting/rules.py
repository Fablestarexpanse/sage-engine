"""Item-template fields crafting claims, and the pure recipe math."""

from pydantic import Field, RootModel


class Recipe(RootModel[dict[str, int]]):
    """`recipe:` — inputs (template id -> count) consumed to craft this item."""


class Yields(RootModel[int]):
    """`yields:` — how many of this item one craft produces (ammo batches etc.)."""

    root: int = Field(ge=1)


class Scraps(RootModel[dict[str, int]]):
    """`scraps:` — deconstruction outputs (template id -> count)."""


def missing_for(recipe: dict[str, int], inventory: list[dict]) -> dict[str, int]:
    """What the recipe still needs given this inventory (empty = craftable)."""
    have: dict[str, int] = {}
    for it in inventory:
        t = it.get("template", "")
        have[t] = have.get(t, 0) + 1
    return {t: n - have.get(t, 0) for t, n in recipe.items() if have.get(t, 0) < n}


def scrap_yield(recipe: dict[str, int], scraps: dict[str, int]) -> dict[str, int]:
    """Deconstruction outputs: explicit scraps, else half the recipe (never nothing)."""
    if scraps:
        return dict(scraps)
    if recipe:
        out = {t: n // 2 for t, n in recipe.items() if n // 2 > 0}
        return out or {next(iter(recipe)): 1}
    return {}
