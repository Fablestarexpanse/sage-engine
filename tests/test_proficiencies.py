"""Proficiency catalog, registry, engine, and character stats helpers."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from fablestar.proficiencies.bonus import (
    CONDUIT_CHARGEN_POINTS_TOTAL,
    calculate_proficiency_bonus,
    validate_chargen_conduit_allocation,
)
from fablestar.proficiencies.catalog_loader import (
    leaf_definitions_from_builtin_rows,
    load_proficiency_catalog_from_disk,
)
from fablestar.proficiencies.data import EXPECTED_LEAF_COUNT, all_builtin_leaf_rows
from fablestar.proficiencies.engine import ProficiencyEngine
from fablestar.proficiencies.registry import ProficiencyRegistry
from fablestar.proficiencies.state_helpers import (
    combat_attack_defense_from_stats,
    ensure_proficiency_block,
    migrate_legacy_stats,
)
from fablestar.proficiencies.validation import validate_leaf_definitions

ROOT = Path(__file__).resolve().parents[1]


class TestBuiltinCatalog(unittest.TestCase):
    def test_leaf_count(self) -> None:
        rows = all_builtin_leaf_rows()
        self.assertEqual(len(rows), EXPECTED_LEAF_COUNT)

    def test_catalog_json_matches_builtin(self) -> None:
        path = ROOT / "content" / "proficiencies" / "catalog.json"
        self.assertTrue(path.is_file(), "run scripts/write_proficiency_catalog_json.py")
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(raw.get("expected_leaf_count"), EXPECTED_LEAF_COUNT)
        self.assertEqual(len(raw.get("leaves", [])), EXPECTED_LEAF_COUNT)

    def test_validation(self) -> None:
        leaves = leaf_definitions_from_builtin_rows()
        ok, errs = validate_leaf_definitions(leaves, expected_count=EXPECTED_LEAF_COUNT)
        self.assertTrue(ok, errs)

    def test_loader_disk(self) -> None:
        doc = load_proficiency_catalog_from_disk(ROOT / "content")
        self.assertEqual(len(doc.leaves), EXPECTED_LEAF_COUNT)


class TestRegistry(unittest.TestCase):
    def test_internal_nodes(self) -> None:
        doc = load_proficiency_catalog_from_disk(ROOT / "content")
        reg = ProficiencyRegistry(doc.leaves)
        self.assertIn("combat.melee", reg.nodes)
        self.assertFalse(reg.nodes["combat.melee"].is_leaf)
        self.assertTrue(reg.nodes["combat.melee.blades"].is_leaf)


class TestEngine(unittest.TestCase):
    def setUp(self) -> None:
        doc = load_proficiency_catalog_from_disk(ROOT / "content")
        self.reg = ProficiencyRegistry(doc.leaves)
        self.engine = ProficiencyEngine(self.reg)

    def test_field_gain_respects_leaf_cap(self) -> None:
        stats = ensure_proficiency_block({})
        prof = stats["conduit"]["proficiencies"]
        prof["combat"] = {"level": 10, "state": "raise", "peak": 10}
        prof["combat.melee"] = {"level": 15, "state": "raise", "peak": 50}
        prof["combat.melee.blades"] = {"level": 200, "state": "raise", "peak": 200}
        r = self.engine.try_field_gain(
            stats,
            leaf_id="combat.melee.blades",
            context={"field_success": True},
        )
        self.assertFalse(r.ok)

    def test_depth_gate_parent_branch(self) -> None:
        stats = ensure_proficiency_block({})
        prof = stats["conduit"]["proficiencies"]
        prof["combat"] = {"level": 10, "state": "raise", "peak": 10}
        prof["combat.melee"] = {"level": 14, "state": "raise", "peak": 14}
        prof["combat.melee.blades"] = {"level": 0, "state": "raise", "peak": 0}
        r = self.engine.try_field_gain(
            stats, "combat.melee.blades", context={"field_success": True}
        )
        self.assertFalse(r.ok)
        self.assertEqual(r.message, "depth_gate")
        prof["combat.melee"]["level"] = 15
        r2 = self.engine.try_field_gain(
            stats, "combat.melee.blades", context={"field_success": True}
        )
        self.assertTrue(r2.ok)

    def test_decay_floor(self) -> None:
        stats = ensure_proficiency_block({})
        prof = stats["conduit"]["proficiencies"]
        prof["combat.melee.blades"] = {"level": 80, "state": "lower", "peak": 100}
        prof["combat.melee.impact"] = {"level": 20, "state": "lower", "peak": 20}
        self.engine.apply_decay(stats, 50)
        b = prof["combat.melee.blades"]
        self.assertGreaterEqual(int(b["level"]), 75)


class TestBonusFormula(unittest.TestCase):
    def test_level_zero_bonus(self) -> None:
        ca = {"FRT": 13, "RFX": 13, "ACU": 13, "RSV": 13, "PRS": 13}
        self.assertEqual(calculate_proficiency_bonus(0, ca, {"RFX": 1.0}), 0)

    def test_bonus_increases_with_level(self) -> None:
        ca = {"FRT": 15, "RFX": 20, "ACU": 13, "RSV": 10, "PRS": 7}
        w = {"FRT": 0.3, "RFX": 0.5, "ACU": 0.2}
        b100 = calculate_proficiency_bonus(100, ca, w)
        b50 = calculate_proficiency_bonus(50, ca, w)
        self.assertGreater(b100, b50)

    def test_chargen_validation(self) -> None:
        ok, _ = validate_chargen_conduit_allocation(
            {"FRT": 13, "RFX": 13, "ACU": 13, "RSV": 13, "PRS": 13}
        )
        self.assertTrue(ok)
        bad, err = validate_chargen_conduit_allocation(
            {"FRT": 13, "RFX": 13, "ACU": 13, "RSV": 13, "PRS": 12}
        )
        self.assertFalse(bad)
        self.assertEqual(err, "conduit_total_not_65")
        self.assertEqual(
            sum([13, 13, 13, 13, 13]),
            CONDUIT_CHARGEN_POINTS_TOTAL,
        )


class TestCharacterHelpers(unittest.TestCase):
    def test_migrate_legacy(self) -> None:
        raw = {"strength": 18, "dexterity": 14, "intelligence": 12, "perception": 10}
        out = migrate_legacy_stats(raw)
        self.assertIn("conduit_attributes", out["conduit"])
        self.assertEqual(out.get("strength"), 18)

    def test_combat_hybrid_ratings(self) -> None:
        stats = ensure_proficiency_block({"strength": 30, "dexterity": 9})
        stats["conduit"]["proficiencies"]["combat.melee.blades"] = {
            "level": 60,
            "state": "raise",
            "peak": 60,
        }
        atk, defe = combat_attack_defense_from_stats(stats, hybrid_legacy=True)
        self.assertGreater(atk, 0)
        self.assertGreater(defe, 0)


if __name__ == "__main__":
    unittest.main()
