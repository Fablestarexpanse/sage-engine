"""AI slots: a world fills a slot with ai/prompts/<slot>.j2; an empty slot is disabled."""

from __future__ import annotations

from pathlib import Path

import pytest

from sage.llm.prompts import ENGINE_SLOTS, PromptManager, SlotDisabled
from sage.world.package import available_worlds, load_world_package

ROOT = Path(__file__).resolve().parents[2]


def test_a_slot_is_enabled_only_by_a_template(tmp_path):
    (tmp_path / "narrate.room.j2").write_text("Describe: {{ observation_block }}", encoding="utf-8")
    prompts = PromptManager(tmp_path)

    assert prompts.enabled("narrate.room")
    assert prompts.render("narrate.room", observation_block="a gate") == "Describe: a gate"
    assert not prompts.enabled("image.scene")
    with pytest.raises(SlotDisabled, match="no template"):
        prompts.render("image.scene", narrative_context="", room_hint="")


def test_templates_for_undeclared_slots_are_not_rendered(tmp_path):
    (tmp_path / "combat.narration.j2").write_text("x", encoding="utf-8")
    prompts = PromptManager(tmp_path)
    assert not prompts.enabled("combat.narration")
    with pytest.raises(SlotDisabled, match="not declared"):
        prompts.render("combat.narration")

    prompts.declare("combat.narration", "combat")
    assert prompts.render("combat.narration") == "x"
    with pytest.raises(ValueError, match="already declared"):
        prompts.declare("combat.narration", "other")
    prompts.withdraw("combat")
    assert "combat.narration" not in prompts.slots()
    assert set(ENGINE_SLOTS) <= set(prompts.slots())  # engine slots are never withdrawn


def test_every_shipped_template_names_a_slot_and_a_world_without_ai_has_none():
    plugin_slots = {"combat.narration"}
    for world_id in available_worlds(ROOT / "worlds"):
        world = load_world_package(ROOT / "worlds" / world_id)
        shipped = {p.name[: -len(".j2")] for p in world.prompts_dir.glob("*.j2")}
        assert shipped <= set(ENGINE_SLOTS) | plugin_slots, (world_id, shipped)
    worlds = [load_world_package(ROOT / "worlds" / w) for w in available_worlds(ROOT / "worlds")]
    assert any(not list(w.prompts_dir.glob("*.j2")) for w in worlds), "a world must run without AI"
