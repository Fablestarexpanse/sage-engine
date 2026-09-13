"""Interface domain leaf definitions (13 leaves per skill tree tables)."""

from __future__ import annotations

from sage.proficiencies.data._types import LeafRow


def interface_leaves() -> list[LeafRow]:
    return [
        ("interface.perception.threat_detection", {"ACU": 0.4, "RSV": 0.3, "RFX": 0.3}),
        ("interface.perception.anomaly_scan", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("interface.perception.entity_analysis", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("interface.neural_link.bandwidth", {"ACU": 0.4, "RSV": 0.4, "RFX": 0.2}),
        ("interface.neural_link.latency", {"RFX": 0.4, "ACU": 0.4, "RSV": 0.2}),
        ("interface.neural_link.stability", {"RSV": 0.5, "FRT": 0.3, "ACU": 0.2}),
        ("interface.data_integration.pattern_memory", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("interface.data_integration.glyph_theory", {"ACU": 0.6, "RSV": 0.3, "RFX": 0.1}),
        ("interface.data_integration.archive_access", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("interface.diagnostics.self_assessment", {"ACU": 0.4, "RSV": 0.4, "FRT": 0.2}),
        ("interface.diagnostics.field_triage", {"ACU": 0.4, "RSV": 0.3, "PRS": 0.3}),
        ("interface.diagnostics.system_analysis", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("interface.diagnostics.resonance_reading", {"ACU": 0.4, "RSV": 0.4, "PRS": 0.2}),
    ]
