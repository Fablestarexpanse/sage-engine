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
    (tmp_path / "config").mkdir()
    monkeypatch.setenv("FABLESTAR_PROJECT_ROOT", str(tmp_path))
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
    assert wf.list_workflows(in_use)[0]["in_use_as"] == ["portrait"]
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
