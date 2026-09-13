"""Builtin leaf row sources merged into the proficiency catalog."""

from __future__ import annotations

from sage.proficiencies.data._types import LeafRow
from sage.proficiencies.data.astronautics import astronautics_leaves
from sage.proficiencies.data.combat import combat_leaves
from sage.proficiencies.data.commerce import commerce_leaves
from sage.proficiencies.data.culture import culture_leaves
from sage.proficiencies.data.fabrication import fabrication_leaves
from sage.proficiencies.data.interface import interface_leaves
from sage.proficiencies.data.medicine import medicine_leaves
from sage.proficiencies.data.resonance import resonance_leaves
from sage.proficiencies.data.signal import signal_leaves
from sage.proficiencies.data.systems import systems_leaves
from sage.proficiencies.data.traversal import traversal_leaves

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
