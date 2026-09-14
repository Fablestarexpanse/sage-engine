"""ComfyUI workflow library: parse/validate, analyze, save, delete, assign."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sage.admin import comfyui_workflows as wf

API_WORKFLOW = {
    "_comment": "notes are allowed",
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad"},
        "_meta": {"title": "Negative"},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "a hero"},
        "_meta": {"title": "Positive Prompt"},
    },
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ["12", 0]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x", "images": ["8", 0]}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl.safetensors"}},
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    from sage.core import config as core_config

    (tmp_path / "config").mkdir()
    monkeypatch.setenv("SAGE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(core_config, "_world_comfyui_dir", None)
    return tmp_path


def cfg(**kw):
    base = {"workflow_path": "", "area_workflow_path": ""}
    base.update(kw)
    return SimpleNamespace(**base)


def test_parse_rejects_ui_graph_and_junk():
    with pytest.raises(ValueError, match="ui_format_workflow"):
        wf.parse_workflow(json.dumps({"nodes": [], "links": []}))
    with pytest.raises(ValueError, match="invalid_json"):
        wf.parse_workflow("{nope")
    with pytest.raises(ValueError, match="not_api_workflow"):
        wf.parse_workflow(json.dumps({"1": {"inputs": {}}}))
    with pytest.raises(ValueError, match="not_api_workflow"):
        wf.parse_workflow(json.dumps({"_comment": "only notes"}))


def test_analyze_finds_prompt_output_and_loader():
    a = wf.analyze_workflow(wf.parse_workflow(json.dumps(API_WORKFLOW)))
    assert a["node_count"] == 5
    assert [n["id"] for n in a["prompt_nodes"]] == ["3", "6"]  # linked text input excluded
    assert a["suggested_prompt_node_id"] == "6"
    assert a["suggested_output_node_id"] == "9"
    assert a["checkpoint_loaders"] == [{"id": "4", "ckpt_name": "sdxl.safetensors"}]


def test_save_list_assign_delete(root):
    name = wf.slugify_name("My Portrait (v2).json")
    assert name == "My_Portrait_v2.json"
    wf.save_workflow(name, json.dumps(API_WORKFLOW))
    with pytest.raises(ValueError, match="name_taken"):
        wf.save_workflow(name, json.dumps(API_WORKFLOW))
    items = wf.list_workflows(cfg())
    assert [(i["name"], i["valid"], i["source"]) for i in items] == [(name, True, "library")]

    patch = wf.assignment_patch(name, "portrait", None, None)
    assert patch == {
        "workflow_path": f"config/comfyui_workflows/{name}",
        "positive_prompt_node_id": "6",
        "output_node_id": "9",
    }
    with pytest.raises(ValueError, match="prompt_node_required"):
        wf.assignment_patch(name, "area", "7", "9")
    with pytest.raises(ValueError, match="output_node_required"):
        wf.assignment_patch(name, "area", "6", "4")

    in_use = cfg(workflow_path=patch["workflow_path"])
    # The area role has no graph of its own, so it runs the portrait graph too.
    assert wf.list_workflows(in_use)[0]["in_use_as"] == ["portrait", "area"]
    with pytest.raises(ValueError, match="workflow_in_use"):
        wf.delete_workflow(name, in_use)
    wf.delete_workflow(name, cfg())
    assert wf.list_workflows(cfg()) == []


def test_names_cannot_escape(root):
    (root / "config" / "server.toml").write_text("secret = 1")
    (root / "config" / "comfyui_portrait.example.json").write_text("{}")
    for bad in (
        "../server.toml",
        "server.toml",
        r"..\server.json",
        "comfyui_portrait.example.json",
        "",
    ):
        assert wf.find_workflow(bad) is None
    with pytest.raises(ValueError, match="invalid_name"):
        wf.save_workflow("../evil.json", json.dumps(API_WORKFLOW))


def test_legacy_files_listed_but_protected(root):
    (root / "config" / "comfyui_scene_workflow.json").write_text(json.dumps(API_WORKFLOW))
    items = wf.list_workflows(cfg(area_workflow_path="config/comfyui_scene_workflow.json"))
    assert items[0]["source"] == "legacy" and items[0]["in_use_as"] == ["area"]
    with pytest.raises(ValueError, match="legacy_workflow_protected"):
        wf.delete_workflow("comfyui_scene_workflow.json", cfg())


def test_world_graphs_are_the_default_listed_and_protected(root, monkeypatch):
    from sage.core import config as core_config
    from sage.core.config import resolve_workflow_path

    world = root / "worlds" / "demo" / "ai" / "comfyui"
    world.mkdir(parents=True)
    (world / "portrait.json").write_text(json.dumps(API_WORKFLOW))
    monkeypatch.setattr(core_config, "_world_comfyui_dir", world)

    assert resolve_workflow_path(cfg(), "portrait") == world / "portrait.json"
    assert resolve_workflow_path(cfg(), "area") == world / "portrait.json"  # no area graph
    # A toml path that no longer exists falls back to the world's graph.
    assert resolve_workflow_path(cfg(workflow_path="config/gone.json"), "portrait") == (
        world / "portrait.json"
    )
    # An existing deployment path wins.
    wf.save_workflow("mine.json", json.dumps(API_WORKFLOW))
    mine = cfg(workflow_path="config/comfyui_workflows/mine.json")
    assert resolve_workflow_path(mine, "portrait").name == "mine.json"

    items = {i["name"]: i for i in wf.list_workflows(cfg())}
    assert items["portrait.json"]["source"] == "world"
    assert items["portrait.json"]["in_use_as"] == ["portrait", "area"]
    with pytest.raises(ValueError, match="world_workflow_protected"):
        wf.delete_workflow("portrait.json", cfg())
