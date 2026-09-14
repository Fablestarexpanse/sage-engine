"""Medicine domain leaf definitions (18)."""

from __future__ import annotations

from ._types import LeafRow


def medicine_leaves() -> list[LeafRow]:
    return [
        ("medicine.trauma.wound_closure", {"RFX": 0.4, "ACU": 0.3, "FRT": 0.3}),
        ("medicine.trauma.bone_setting", {"RFX": 0.4, "ACU": 0.4, "FRT": 0.2}),
        ("medicine.trauma.burn_treatment", {"ACU": 0.4, "RFX": 0.4, "RSV": 0.2}),
        ("medicine.trauma.toxin_purge", {"ACU": 0.5, "RFX": 0.3, "FRT": 0.2}),
        ("medicine.surgery.field_surgery", {"RFX": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("medicine.surgery.implant_work", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("medicine.surgery.glyph_excision", {"ACU": 0.4, "RFX": 0.3, "RSV": 0.3}),
        ("medicine.surgery.reconstructive", {"RFX": 0.4, "ACU": 0.4, "RSV": 0.2}),
        ("medicine.psychiatry.drift_therapy", {"RSV": 0.4, "ACU": 0.3, "PRS": 0.3}),
        ("medicine.psychiatry.trauma_counseling", {"PRS": 0.4, "RSV": 0.3, "ACU": 0.3}),
        ("medicine.psychiatry.addiction_treatment", {"RSV": 0.4, "PRS": 0.3, "ACU": 0.3}),
        ("medicine.psychiatry.cognitive_rehab", {"ACU": 0.4, "RSV": 0.4, "PRS": 0.2}),
        ("medicine.pharmacology.dosing", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("medicine.pharmacology.compound_analysis", {"ACU": 0.6, "RSV": 0.2, "RFX": 0.2}),
        ("medicine.pharmacology.custom_formulation", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("medicine.diagnostics.patient_assessment", {"ACU": 0.4, "RSV": 0.3, "PRS": 0.3}),
        ("medicine.diagnostics.epidemiology", {"ACU": 0.5, "PRS": 0.3, "RSV": 0.2}),
        ("medicine.diagnostics.forensic_analysis", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
    ]
