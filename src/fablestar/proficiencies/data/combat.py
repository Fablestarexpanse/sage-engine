"""Combat domain leaf definitions (stat weights sum to 1.0)."""

from __future__ import annotations

from fablestar.proficiencies.data._types import LeafRow


def combat_leaves() -> list[LeafRow]:
    return [
        ("combat.melee.blades", {"RFX": 0.5, "FRT": 0.3, "ACU": 0.2}),
        ("combat.melee.impact", {"FRT": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("combat.melee.polearms", {"FRT": 0.4, "RFX": 0.4, "ACU": 0.2}),
        ("combat.melee.unarmed", {"RFX": 0.4, "FRT": 0.3, "RSV": 0.2, "ACU": 0.1}),
        ("combat.ballistic.sidearms", {"RFX": 0.5, "ACU": 0.3, "FRT": 0.2}),
        ("combat.ballistic.longarms", {"RFX": 0.4, "ACU": 0.4, "FRT": 0.2}),
        ("combat.ballistic.heavy_weapons", {"FRT": 0.4, "RFX": 0.3, "ACU": 0.3}),
        ("combat.ballistic.specialty_weapons", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("combat.energy_weapons.beam", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("combat.energy_weapons.pulse", {"RFX": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("combat.energy_weapons.arc", {"ACU": 0.4, "RSV": 0.3, "RFX": 0.3}),
        ("combat.energy_weapons.resonance_arms", {"RSV": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("combat.explosives.grenades", {"RFX": 0.4, "ACU": 0.3, "FRT": 0.3}),
        ("combat.explosives.mines_traps", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("combat.explosives.rockets", {"ACU": 0.4, "RFX": 0.3, "FRT": 0.3}),
        ("combat.explosives.demolitions", {"ACU": 0.5, "FRT": 0.3, "RSV": 0.2}),
        ("combat.defense.parry", {"RFX": 0.5, "FRT": 0.3, "ACU": 0.2}),
        ("combat.defense.evasion", {"RFX": 0.5, "ACU": 0.3, "FRT": 0.2}),
        ("combat.defense.armor_systems", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("combat.defense.field_barriers", {"ACU": 0.4, "FRT": 0.3, "RSV": 0.3}),
        ("combat.tactics.threat_assessment", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("combat.tactics.positioning", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("combat.tactics.squad_doctrine", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("combat.tactics.ambush", {"ACU": 0.4, "RFX": 0.3, "RSV": 0.3}),
        ("combat.specialist.entity_hunting", {"ACU": 0.4, "RSV": 0.3, "RFX": 0.3}),
        ("combat.specialist.breaching", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("combat.specialist.suppression", {"PRS": 0.3, "FRT": 0.3, "ACU": 0.2, "RFX": 0.2}),
        ("combat.vehicle_combat.mech_piloting", {"RFX": 0.4, "ACU": 0.3, "FRT": 0.3}),
        ("combat.vehicle_combat.mech_weapons", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("combat.vehicle_combat.ground_vehicle", {"RFX": 0.4, "ACU": 0.3, "FRT": 0.3}),
        ("combat.vehicle_combat.atmospheric", {"RFX": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("combat.vehicle_combat.drone_command", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
    ]
