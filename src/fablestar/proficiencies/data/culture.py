"""Culture domain leaf definitions (30)."""

from __future__ import annotations

LeafRow = tuple[str, dict[str, float]]


def culture_leaves() -> list[LeafRow]:
    return [
        ("culture.governance.administration", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("culture.governance.legislation", {"ACU": 0.4, "PRS": 0.4, "RSV": 0.2}),
        ("culture.governance.diplomacy", {"PRS": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("culture.governance.public_policy", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("culture.governance.colonial_admin", {"ACU": 0.3, "PRS": 0.3, "RSV": 0.2, "FRT": 0.2}),
        ("culture.governance.interplanetary_law", {"ACU": 0.4, "PRS": 0.4, "RSV": 0.2}),
        ("culture.law.investigation", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("culture.law.prosecution", {"PRS": 0.4, "ACU": 0.4, "RSV": 0.2}),
        ("culture.law.defense_advocacy", {"PRS": 0.4, "ACU": 0.4, "RSV": 0.2}),
        ("culture.law.arbitration", {"PRS": 0.4, "RSV": 0.3, "ACU": 0.3}),
        ("culture.law.regulatory_compliance", {"ACU": 0.5, "PRS": 0.3, "RSV": 0.2}),
        ("culture.performance.music", {"RFX": 0.3, "PRS": 0.3, "RSV": 0.2, "ACU": 0.2}),
        ("culture.performance.storytelling", {"PRS": 0.5, "RSV": 0.3, "ACU": 0.2}),
        ("culture.performance.acting", {"PRS": 0.4, "RSV": 0.3, "ACU": 0.3}),
        ("culture.performance.visual_art", {"ACU": 0.3, "RFX": 0.3, "PRS": 0.2, "RSV": 0.2}),
        ("culture.performance.digital_media", {"ACU": 0.4, "RFX": 0.3, "PRS": 0.3}),
        ("culture.education.instruction", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("culture.education.curriculum_design", {"ACU": 0.5, "PRS": 0.3, "RSV": 0.2}),
        ("culture.education.research_methods", {"ACU": 0.6, "RSV": 0.2, "RFX": 0.2}),
        ("culture.education.archival_science", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("culture.media.journalism", {"ACU": 0.3, "PRS": 0.4, "RSV": 0.3}),
        ("culture.media.propaganda", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("culture.media.publishing", {"ACU": 0.4, "PRS": 0.3, "RFX": 0.3}),
        ("culture.media.public_relations", {"PRS": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("culture.community.event_planning", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("culture.community.counseling", {"PRS": 0.4, "RSV": 0.4, "ACU": 0.2}),
        ("culture.community.chaplaincy", {"RSV": 0.4, "PRS": 0.4, "ACU": 0.2}),
        ("culture.community.recruitment", {"PRS": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("culture.community.morale_management", {"PRS": 0.4, "RSV": 0.4, "ACU": 0.2}),
        ("culture.community.conflict_resolution", {"PRS": 0.4, "RSV": 0.3, "ACU": 0.3}),
    ]
