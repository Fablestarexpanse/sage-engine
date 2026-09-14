"""Morality: one number, a character's moral standing from -100 (evil) to +100 (good).

Nothing in play changes it yet; staff set it through the character stats JSON. The panel shows
the standing on its range with a band name from the lexicon.
"""

from __future__ import annotations

from typing import Any

from sage.api import PluginAPI

BLOCK = "morality"
LOW, HIGH = -100, 100
# Upper bound (inclusive) of each band, lowest first; names are lexicon keys morality.band.<id>.
BANDS = (("evil", -60), ("dark", -20), ("neutral", 19), ("decent", 59), ("good", HIGH))


def standing_of(stats: dict[str, Any]) -> int:
    block = stats.get(BLOCK)
    value = block.get("standing", 0) if isinstance(block, dict) else 0
    return max(LOW, min(HIGH, int(value or 0)))


def band_of(standing: int) -> str:
    return next(name for name, upper in BANDS if standing <= upper)


def setup(api: PluginAPI) -> None:
    api.state.block(BLOCK, default=lambda: {"standing": 0})

    def panel(name: str, stats: dict[str, Any]) -> dict[str, Any]:
        standing = standing_of(stats)
        band = band_of(standing)
        tone = {"evil": "bad", "dark": "warn", "good": "good", "decent": "good"}.get(band)
        row = {
            "label": api.t("morality.label.standing"),
            "value": standing,
            "min": LOW,
            "max": HIGH,
            "note": api.t(f"morality.band.{band}"),
        }
        if tone:
            row["tone"] = tone
        return {"stats": [row]}

    api.snapshot.contribute(BLOCK, panel)
    api.ui.panel("standing", "stat_sheet", BLOCK, icon="⚖")
