"""Declarative client panels (contracts catalog #11).

A plugin declares a panel: an id, a kind, and the snapshot section that carries its data. The
engine sends the specs with the character snapshot; the player client draws every kind with one
generic renderer, so no plugin ships client code (``kind = "module"`` is reserved and refused).

Data shapes, by kind (the section's value):

``key_value``   ``{"rows": [{"label": str, "value": str | number}]}``
``list``        ``{"items": [{"label": str, "detail"?: str, "value"?: str | number,
                "tone"?: "good" | "warn" | "bad"}], "empty"?: str}``
``stat_sheet``  ``{"stats": [{"label": str, "value": number, "min"?: number, "max"?: number,
                "note"?: str, "tone"?: str}]}`` (a bar is drawn when ``max`` is given; ``min``
                defaults to 0)
``wallet``      ``{"balances": [{"label": str, "amount": number}]}``
``table``       ``{"columns": [str], "rows": [[str | number]]}``
``tree``        ``{"nodes": [node]}``, node = ``{"id": str, "label": str, "value"?: number,
                "max"?: number, "note"?: str, "tone"?: str, "children"?: [node],
                "actions"?: [{"label": str, "command": str}]}``

An action's ``command`` is sent as if the player typed it, so a panel can do nothing its
commands can't. Text in the data is already player-facing (plugins resolve lexicon keys).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sage import lexicon

PANEL_KINDS = ("key_value", "list", "stat_sheet", "wallet", "table", "tree")
# Reserved for plugin-shipped client code (DECISIONS G.10): accepted by name, refused at boot.
RESERVED_KINDS = ("module",)


@dataclass(frozen=True)
class Panel:
    id: str
    owner: str
    kind: str
    section: str
    icon: str = ""

    @property
    def title_key(self) -> str:
        owner, _, name = self.id.partition(".")
        return f"{owner}.panel.{name}"


class PanelRegistry:
    def __init__(self) -> None:
        self._panels: list[Panel] = []

    def add(self, panel: Panel) -> None:
        if panel.kind in RESERVED_KINDS:
            raise ValueError(
                f"panel kind {panel.kind!r} (plugin-shipped client code) is not supported in "
                "this engine version"
            )
        if panel.kind not in PANEL_KINDS:
            raise ValueError(f"unknown panel kind {panel.kind!r}; use one of {PANEL_KINDS}")
        if any(p.id == panel.id for p in self._panels):
            raise ValueError(f"panel {panel.id!r} is already declared")
        self._panels.append(panel)

    def withdraw(self, owner: str) -> None:
        self._panels = [p for p in self._panels if p.owner != owner]

    def specs(self) -> list[dict[str, Any]]:
        """What the client needs to draw each panel (titles resolved in the active lexicon)."""
        return [
            {
                "id": p.id,
                "kind": p.kind,
                "title": lexicon.t(p.title_key),
                "icon": p.icon,
                "section": p.section,
            }
            for p in self._panels
        ]
