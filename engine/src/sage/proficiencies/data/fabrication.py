"""Fabrication domain leaf definitions (37)."""

from __future__ import annotations

from sage.proficiencies.data._types import LeafRow


def fabrication_leaves() -> list[LeafRow]:
    return [
        ("fabrication.weaponsmithing.blade_forging", {"RFX": 0.4, "ACU": 0.3, "FRT": 0.3}),
        ("fabrication.weaponsmithing.ballistics", {"ACU": 0.5, "RFX": 0.3, "FRT": 0.2}),
        ("fabrication.weaponsmithing.energy_weapons", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("fabrication.weaponsmithing.glyph_integration", {"ACU": 0.4, "RSV": 0.3, "RFX": 0.3}),
        ("fabrication.armorcraft.plating", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("fabrication.armorcraft.weave", {"RFX": 0.4, "ACU": 0.4, "FRT": 0.2}),
        ("fabrication.armorcraft.shield_systems", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("fabrication.armorcraft.environmental_seal", {"ACU": 0.4, "FRT": 0.3, "RFX": 0.3}),
        ("fabrication.devices.sensors", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("fabrication.devices.comm_gear", {"ACU": 0.5, "RFX": 0.3, "PRS": 0.2}),
        ("fabrication.devices.medical_equipment", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("fabrication.devices.utility_tools", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("fabrication.chemistry.stimulants", {"ACU": 0.5, "RSV": 0.3, "FRT": 0.2}),
        ("fabrication.chemistry.reagents", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("fabrication.chemistry.compounds", {"ACU": 0.5, "FRT": 0.3, "RFX": 0.2}),
        ("fabrication.chemistry.pharmaceuticals", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("fabrication.salvage.disassembly", {"ACU": 0.4, "RFX": 0.3, "FRT": 0.3}),
        ("fabrication.salvage.reclamation", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("fabrication.salvage.repurposing", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("fabrication.materials.metallurgy", {"ACU": 0.4, "FRT": 0.3, "RFX": 0.3}),
        ("fabrication.materials.composites", {"ACU": 0.5, "RFX": 0.3, "FRT": 0.2}),
        ("fabrication.shipbuilding.hull_construction", {"FRT": 0.3, "ACU": 0.4, "RFX": 0.3}),
        ("fabrication.shipbuilding.drive_systems", {"ACU": 0.5, "RFX": 0.3, "FRT": 0.2}),
        ("fabrication.shipbuilding.weapons_installation", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("fabrication.shipbuilding.avionics", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("fabrication.shipbuilding.interior_fitting", {"ACU": 0.4, "RFX": 0.3, "PRS": 0.3}),
        ("fabrication.vehicle_construction.frame_assembly", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("fabrication.vehicle_construction.drive_train", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("fabrication.vehicle_construction.weapon_mounting", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("fabrication.vehicle_construction.armor_plating", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("fabrication.robotics.drone_construction", {"ACU": 0.5, "RFX": 0.3, "FRT": 0.2}),
        ("fabrication.robotics.drone_programming", {"ACU": 0.6, "RSV": 0.2, "RFX": 0.2}),
        ("fabrication.robotics.android_construction", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("fabrication.robotics.autonomous_systems", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("fabrication.repair.weapons_armor", {"RFX": 0.4, "ACU": 0.4, "FRT": 0.2}),
        ("fabrication.repair.electronics", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("fabrication.repair.structural", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
    ]
