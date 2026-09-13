"""Astronautics domain leaf definitions (25)."""

from __future__ import annotations

from sage.proficiencies.data._types import LeafRow


def astronautics_leaves() -> list[LeafRow]:
    return [
        ("astronautics.piloting.small_craft", {"RFX": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("astronautics.piloting.medium_vessels", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("astronautics.piloting.large_vessels", {"ACU": 0.4, "RSV": 0.3, "PRS": 0.3}),
        ("astronautics.piloting.capital_ships", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("astronautics.piloting.docking", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("astronautics.astrogation.route_calculation", {"ACU": 0.6, "RSV": 0.2, "RFX": 0.2}),
        ("astronautics.astrogation.hazard_avoidance", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("astronautics.astrogation.fuel_optimization", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("astronautics.ship_combat.gunnery", {"RFX": 0.4, "ACU": 0.4, "RSV": 0.2}),
        ("astronautics.ship_combat.missile_systems", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("astronautics.ship_combat.point_defense", {"RFX": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("astronautics.ship_combat.electronic_warfare", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("astronautics.ship_combat.tactical_maneuvering", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("astronautics.ship_systems.propulsion", {"ACU": 0.4, "RFX": 0.3, "FRT": 0.3}),
        ("astronautics.ship_systems.life_support_ship", {"ACU": 0.4, "FRT": 0.3, "RSV": 0.3}),
        ("astronautics.ship_systems.weapons_maintenance", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("astronautics.ship_systems.shields", {"ACU": 0.4, "RSV": 0.3, "RFX": 0.3}),
        ("astronautics.ship_systems.sensors", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("astronautics.eva.hull_work", {"FRT": 0.3, "RFX": 0.4, "ACU": 0.3}),
        ("astronautics.eva.salvage_ops", {"ACU": 0.4, "RFX": 0.3, "FRT": 0.3}),
        ("astronautics.eva.zero_g_combat", {"RFX": 0.4, "FRT": 0.3, "ACU": 0.3}),
        ("astronautics.cargo.loading", {"ACU": 0.3, "FRT": 0.4, "RFX": 0.3}),
        ("astronautics.cargo.hazmat_handling", {"ACU": 0.4, "FRT": 0.3, "RSV": 0.3}),
        ("astronautics.cargo.customs_procedures", {"ACU": 0.4, "PRS": 0.4, "RSV": 0.2}),
        ("astronautics.cargo.contraband", {"ACU": 0.4, "RFX": 0.3, "PRS": 0.3}),
    ]
