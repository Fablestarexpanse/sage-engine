"""Traversal domain leaf definitions."""

from __future__ import annotations

from fablestar.proficiencies.data._types import LeafRow


def traversal_leaves() -> list[LeafRow]:
    return [
        ("traversal.navigation.pathfinding", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("traversal.navigation.orientation", {"RSV": 0.4, "ACU": 0.4, "RFX": 0.2}),
        ("traversal.navigation.depth_reading", {"ACU": 0.4, "RSV": 0.4, "RFX": 0.2}),
        ("traversal.movement.climbing", {"FRT": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("traversal.movement.crawling", {"RFX": 0.4, "FRT": 0.3, "ACU": 0.3}),
        ("traversal.movement.freefall", {"RFX": 0.5, "FRT": 0.3, "RSV": 0.2}),
        ("traversal.movement.swimming", {"FRT": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("traversal.labyrinth_sense.shift_prediction", {"ACU": 0.5, "RSV": 0.4, "RFX": 0.1}),
        ("traversal.labyrinth_sense.resonance_trail", {"ACU": 0.4, "RSV": 0.4, "RFX": 0.2}),
        ("traversal.labyrinth_sense.dead_zone_nav", {"RSV": 0.4, "FRT": 0.3, "ACU": 0.3}),
        ("traversal.survival.resource_mgmt", {"ACU": 0.4, "RSV": 0.3, "FRT": 0.3}),
        ("traversal.survival.hazard_resist", {"FRT": 0.5, "RSV": 0.3, "ACU": 0.2}),
        ("traversal.survival.emergency_evac", {"RFX": 0.4, "ACU": 0.3, "FRT": 0.3}),
        ("traversal.wilderness.tracking", {"ACU": 0.4, "RFX": 0.3, "RSV": 0.3}),
        ("traversal.wilderness.terrain_adaptation", {"FRT": 0.4, "RFX": 0.3, "ACU": 0.3}),
    ]
