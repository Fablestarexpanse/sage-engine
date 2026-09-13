"""Typed resolver slots (docs/sage/PHASE1_CONTRACTS.md D.B, catalog #4).

A slot is a decision with exactly one answer: the engine (or a plugin) defines it with a
default, and at most one other owner may provide a replacement. Two providers for one slot
is a configuration error, raised immediately rather than resolved by load order.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class ResolverError(RuntimeError):
    """Unknown slot, duplicate definition, or two providers for one slot."""


@dataclass
class _Slot:
    default: Callable[..., Any]
    defined_by: str
    provider: Callable[..., Any] | None = None
    provided_by: str | None = None


class Resolvers:
    def __init__(self) -> None:
        self._slots: dict[str, _Slot] = {}

    def define(self, slot: str, default: Callable[..., Any], owner: str = "sage") -> None:
        if slot in self._slots:
            raise ResolverError(
                f"resolver slot {slot!r} already defined by {self._slots[slot].defined_by!r}"
            )
        self._slots[slot] = _Slot(default, owner)

    def provide(self, slot: str, fn: Callable[..., Any], owner: str) -> None:
        entry = self._slots.get(slot)
        if entry is None:
            raise ResolverError(f"cannot provide unknown resolver slot {slot!r}")
        if entry.provider is not None:
            raise ResolverError(
                f"resolver slot {slot!r} already provided by {entry.provided_by!r}; "
                f"{owner!r} cannot provide it too"
            )
        entry.provider, entry.provided_by = fn, owner

    def withdraw(self, owner: str) -> None:
        for entry in self._slots.values():
            if entry.provided_by == owner:
                entry.provider = entry.provided_by = None

    def get(self, slot: str) -> Callable[..., Any]:
        entry = self._slots.get(slot)
        if entry is None:
            raise ResolverError(f"unknown resolver slot {slot!r}")
        return entry.provider or entry.default

    def owner(self, slot: str) -> str:
        entry = self._slots[slot]
        return entry.provided_by or entry.defined_by

    def slots(self) -> list[str]:
        return sorted(self._slots)
