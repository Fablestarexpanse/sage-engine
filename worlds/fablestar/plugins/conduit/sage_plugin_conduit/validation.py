"""Catalog integrity checks (used by loader and tests)."""

from __future__ import annotations

from collections.abc import Iterable

from .models import ProficiencyLeafDefinition


def _effective_depth(leaf: ProficiencyLeafDefinition) -> int:
    if leaf.tree_depth and leaf.tree_depth > 0:
        return max(1, min(4, leaf.tree_depth))
    return max(1, min(4, len(leaf.id.split("."))))


def validate_leaf_definitions(
    leaves: list[ProficiencyLeafDefinition],
    expected_count: int | None = None,
) -> tuple[bool, list[str]]:
    """Return (ok, error_messages)."""
    errors: list[str] = []
    seen: set[str] = set()
    for leaf in leaves:
        if leaf.id in seen:
            errors.append(f"duplicate leaf id: {leaf.id}")
        seen.add(leaf.id)
        first = leaf.id.split(".")[0] if leaf.id else ""
        if leaf.domain and first != leaf.domain:
            errors.append(
                f"domain mismatch for {leaf.id} (domain field={leaf.domain}, id root={first})"
            )
        parts = leaf.id.split(".")
        if len(parts) < 2:
            errors.append(f"leaf id must have at least domain.branch: {leaf.id}")
        d = _effective_depth(leaf)
        if d > 4:
            errors.append(f"tree depth > 4 for {leaf.id}")

    if expected_count is not None and len(leaves) != expected_count:
        errors.append(f"leaf count {len(leaves)} != expected {expected_count}")

    return (len(errors) == 0, errors)


def prefix_closure(leaf_ids: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for lid in leaf_ids:
        parts = lid.split(".")
        for i in range(1, len(parts) + 1):
            out.add(".".join(parts[:i]))
    return out
