"""Room observation builder — assembles structured facts from a RoomModel for LLM narration."""

from typing import Any

from sage.world.models import RoomModel


def build_room_fact_block(room: RoomModel, context: dict[str, Any] | None = None) -> str:
    """Converts a RoomModel into a structured fact-block for LLM grounding."""
    context = context or {}

    facts = []
    facts.append(f"Location Type: {room.type}")
    facts.append(f"Depth Level: {room.depth}")

    # Base description from engine
    facts.append(f"Engine Base Description: {room.description.get('base', '')}")

    # Exits
    if room.exits:
        exit_list = ", ".join(room.exits.keys())
        facts.append(f"Visible Exits: {exit_list}")

    # Features
    if room.features:
        feature_list = ", ".join([f.name for f in room.features])
        facts.append(f"Key Features: {feature_list}")

    # Tags (Atmosphere)
    if room.tags:
        tag_list = ", ".join(room.tags)
        facts.append(f"Ambient Atmosphere Tags: {tag_list}")

    # Temporal context (if provided)
    if "time_of_day" in context:
        facts.append(f"Current Time: {context['time_of_day']}")

    return "\n".join(facts)
