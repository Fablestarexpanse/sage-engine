"""Signal domain leaf definitions (16)."""

from __future__ import annotations

from sage.proficiencies.data._types import LeafRow


def signal_leaves() -> list[LeafRow]:
    return [
        ("signal.communication.tactical_relay", {"ACU": 0.4, "RSV": 0.3, "PRS": 0.3}),
        ("signal.communication.encoding", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("signal.communication.translation", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("signal.communication.broadcasting", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("signal.influence.persuasion", {"PRS": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("signal.influence.intimidation", {"PRS": 0.4, "FRT": 0.2, "RSV": 0.3, "ACU": 0.1}),
        ("signal.influence.deception", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("signal.influence.rapport", {"PRS": 0.5, "RSV": 0.3, "ACU": 0.2}),
        ("signal.coordination.squad_command", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("signal.coordination.mentoring", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("signal.coordination.rallying", {"PRS": 0.5, "RSV": 0.3, "FRT": 0.2}),
        ("signal.coordination.logistics_direction", {"ACU": 0.4, "PRS": 0.4, "RSV": 0.2}),
        ("signal.intelligence.labyrinth_history", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("signal.intelligence.entity_taxonomy", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("signal.intelligence.glyph_archaeology", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("signal.intelligence.network_analysis", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
    ]
