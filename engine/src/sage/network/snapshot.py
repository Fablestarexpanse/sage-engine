"""Snapshot contributors (contracts catalog #8): named sections of the client character snapshot.

The engine sends vitals, location, effects, inventory and the map itself. Everything else a client
panel shows comes from a contributor: ``fn(character_name, stats) -> data`` (sync or async),
registered under a section name and called in registration order. A failing contributor is logged
and its section left out; it never breaks the snapshot.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class SnapshotContributors:
    def __init__(self) -> None:
        self._entries: list[tuple[str, str, Callable[[str, dict[str, Any]], Any]]] = []

    def add(self, section: str, fn: Callable[[str, dict[str, Any]], Any], owner: str) -> None:
        if any(s == section for _, s, _ in self._entries):
            raise ValueError(f"snapshot section {section!r} is already contributed")
        self._entries.append((owner, section, fn))

    def withdraw(self, owner: str) -> None:
        self._entries = [e for e in self._entries if e[0] != owner]

    def sections(self) -> list[str]:
        return [section for _, section, _ in self._entries]

    async def build(self, character: str, stats: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for owner, section, fn in list(self._entries):
            try:
                value = fn(character, stats)
                out[section] = await value if inspect.isawaitable(value) else value
            except Exception:
                logger.warning(
                    "Snapshot section %s (owner %s) failed", section, owner, exc_info=True
                )
        return out


def progression_section(resolvers: Any) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """The engine's own section: the world's single progress number (progression.total_levels)."""
    from sage.world.progression import TOTAL_LEVELS

    def contribute(character: str, stats: dict[str, Any]) -> dict[str, Any]:
        return {"levels_total": int(resolvers.get(TOTAL_LEVELS)(stats))}

    return contribute
