"""Builtin leaf row sources merged into the proficiency catalog."""

from __future__ import annotations

from ._types import LeafRow
from .astronautics import astronautics_leaves
from .combat import combat_leaves
from .commerce import commerce_leaves
from .culture import culture_leaves
from .fabrication import fabrication_leaves
from .interface import interface_leaves
from .medicine import medicine_leaves
from .resonance import resonance_leaves
from .signal import signal_leaves
from .systems import systems_leaves
from .traversal import traversal_leaves

EXPECTED_LEAF_COUNT = 278


def all_builtin_leaf_rows() -> list[LeafRow]:
    rows: list[LeafRow] = []
    rows.extend(combat_leaves())
    rows.extend(resonance_leaves())
    rows.extend(interface_leaves())
    rows.extend(traversal_leaves())
    rows.extend(fabrication_leaves())
    rows.extend(signal_leaves())
    rows.extend(medicine_leaves())
    rows.extend(commerce_leaves())
    rows.extend(systems_leaves())
    rows.extend(culture_leaves())
    rows.extend(astronautics_leaves())
    return rows
