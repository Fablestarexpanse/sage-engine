"""Resonance domain leaf definitions."""

from __future__ import annotations

from ._types import LeafRow


def resonance_leaves() -> list[LeafRow]:
    return [
        ("resonance.thermal.ignition", {"ACU": 0.4, "RSV": 0.3, "RFX": 0.2, "FRT": 0.1}),
        ("resonance.thermal.extraction", {"ACU": 0.4, "RSV": 0.4, "RFX": 0.2}),
        ("resonance.thermal.thermal_shaping", {"RSV": 0.4, "ACU": 0.4, "RFX": 0.2}),
        ("resonance.kinetic.force_projection", {"RSV": 0.4, "FRT": 0.3, "ACU": 0.3}),
        ("resonance.kinetic.binding", {"ACU": 0.4, "RSV": 0.4, "RFX": 0.2}),
        ("resonance.kinetic.acceleration", {"RFX": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("resonance.spatial.warding", {"RSV": 0.4, "ACU": 0.4, "FRT": 0.2}),
        ("resonance.spatial.displacement", {"RFX": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("resonance.spatial.folding", {"ACU": 0.5, "RSV": 0.4, "RFX": 0.1}),
        ("resonance.temporal.dilation", {"ACU": 0.5, "RSV": 0.4, "RFX": 0.1}),
        ("resonance.temporal.reversion", {"RSV": 0.5, "ACU": 0.4, "FRT": 0.1}),
        ("resonance.temporal.echo", {"ACU": 0.4, "RSV": 0.4, "RFX": 0.2}),
        ("resonance.neural.suppression", {"RSV": 0.4, "ACU": 0.3, "PRS": 0.3}),
        ("resonance.neural.domination", {"RSV": 0.4, "PRS": 0.3, "ACU": 0.3}),
        ("resonance.neural.communion", {"ACU": 0.4, "RSV": 0.3, "PRS": 0.3}),
        ("resonance.harmonics.amplification", {"RSV": 0.4, "PRS": 0.3, "ACU": 0.3}),
        ("resonance.harmonics.dampening", {"RSV": 0.5, "ACU": 0.3, "FRT": 0.2}),
        ("resonance.harmonics.synchronization", {"PRS": 0.4, "RSV": 0.3, "ACU": 0.3}),
        ("resonance.inscription.etching", {"RFX": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("resonance.inscription.substrate_prep", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("resonance.inscription.stabilization", {"ACU": 0.4, "RSV": 0.4, "RFX": 0.2}),
        ("resonance.attunement.channeling_efficiency", {"RSV": 0.5, "ACU": 0.3, "FRT": 0.2}),
        ("resonance.attunement.recovery", {"FRT": 0.4, "RSV": 0.4, "ACU": 0.2}),
        ("resonance.attunement.overload_tolerance", {"FRT": 0.4, "RSV": 0.4, "ACU": 0.2}),
    ]
