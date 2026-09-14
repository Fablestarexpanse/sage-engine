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


def test_style_file_reaches_templates_and_reloads(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "narrate.room.j2").write_text(
        "[{{ style.tone }}] {{ observation_block }}", encoding="utf-8"
    )
    style = tmp_path / "style.yaml"
    style.write_text(
        "tone: grim\nsystem_prompt: Speak plainly.\ncontent_rules: ['gold']\n", encoding="utf-8"
    )
    prompts = PromptManager(prompts_dir, style)

    assert prompts.render("narrate.room", observation_block="a gate") == "[grim] a gate"
    assert prompts.style.system_prompt == "Speak plainly."
    assert prompts.style.rules() == ["gold"]

    style.write_text("tone: bright\n", encoding="utf-8")
    prompts.reload()
    assert prompts.render("narrate.room", observation_block="a gate") == "[bright] a gate"
    assert "level" in " ".join(prompts.style.rules())  # no rules given: engine defaults


def test_a_broken_style_file_falls_back_to_defaults(tmp_path):
    style = tmp_path / "style.yaml"
    style.write_text("content_rules: ['(unclosed']\n", encoding="utf-8")
    assert PromptManager(tmp_path, style).style.tone == ""
    assert PromptManager(tmp_path, tmp_path / "missing.yaml").style.image.negative == ""
