"""Systems domain leaf definitions (33)."""

from __future__ import annotations

from fablestar.proficiencies.data._types import LeafRow


def systems_leaves() -> list[LeafRow]:
    return [
        ("systems.structural.construction", {"FRT": 0.3, "ACU": 0.4, "RFX": 0.3}),
        ("systems.structural.reinforcement", {"FRT": 0.4, "ACU": 0.4, "RFX": 0.2}),
        ("systems.structural.demolition", {"ACU": 0.4, "FRT": 0.3, "RFX": 0.3}),
        ("systems.structural.architecture", {"ACU": 0.6, "RSV": 0.2, "RFX": 0.2}),
        ("systems.structural.urban_planning", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("systems.power.generation", {"ACU": 0.5, "FRT": 0.3, "RFX": 0.2}),
        ("systems.power.distribution", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("systems.power.storage", {"ACU": 0.5, "FRT": 0.3, "RFX": 0.2}),
        ("systems.power.emergency", {"ACU": 0.4, "RSV": 0.4, "FRT": 0.2}),
        ("systems.life_support.atmosphere", {"ACU": 0.5, "FRT": 0.3, "RSV": 0.2}),
        ("systems.life_support.water_systems", {"ACU": 0.5, "FRT": 0.3, "RFX": 0.2}),
        ("systems.life_support.temperature", {"ACU": 0.4, "FRT": 0.3, "RFX": 0.3}),
        ("systems.life_support.waste_management", {"ACU": 0.4, "FRT": 0.4, "RSV": 0.2}),
        ("systems.computing.programming", {"ACU": 0.6, "RSV": 0.2, "RFX": 0.2}),
        ("systems.computing.network_admin", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("systems.computing.data_recovery", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("systems.computing.security_systems", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("systems.computing.glyphstream_tech", {"ACU": 0.4, "RSV": 0.3, "RFX": 0.3}),
        ("systems.mechanical.maintenance", {"ACU": 0.3, "RFX": 0.4, "FRT": 0.3}),
        ("systems.mechanical.hydraulics", {"ACU": 0.4, "FRT": 0.3, "RFX": 0.3}),
        ("systems.mechanical.robotics_maintenance", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("systems.mechanical.vehicle_maintenance", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("systems.civil.road_systems", {"ACU": 0.4, "FRT": 0.3, "PRS": 0.3}),
        ("systems.civil.water_infrastructure", {"ACU": 0.5, "FRT": 0.3, "RSV": 0.2}),
        ("systems.civil.communications_grid", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("systems.civil.public_transit", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("systems.defense.fortification", {"FRT": 0.3, "ACU": 0.4, "RFX": 0.3}),
        ("systems.defense.turret_systems", {"ACU": 0.5, "RFX": 0.3, "FRT": 0.2}),
        ("systems.defense.barrier_tech", {"ACU": 0.4, "RSV": 0.3, "FRT": 0.3}),
        ("systems.defense.planetary_defense", {"ACU": 0.4, "FRT": 0.3, "RSV": 0.3}),
        ("systems.environmental.contamination_control", {"ACU": 0.4, "FRT": 0.4, "RSV": 0.2}),
        ("systems.environmental.ecosystem_mgmt", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("systems.environmental.terraforming_basics", {"ACU": 0.5, "RSV": 0.3, "FRT": 0.2}),
    ]
