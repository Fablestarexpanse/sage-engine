"""ComfyUI workflow library — list, inspect, upload, delete and assign API-format workflow files.

Files live in ``config/comfyui_workflows/`` (uploads) and, for the originally
shipped graphs, ``config/comfyui_*.json``. Only plain ``*.json`` names are
accepted, so a name can never point outside those two directories.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fablestar.core.config import resolve_project_root

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\.json$")
MAX_WORKFLOW_BYTES = 2 * 1024 * 1024
ROLES = ("portrait", "area")


def library_dir() -> Path:
    return resolve_project_root() / "config" / "comfyui_workflows"


def legacy_dir() -> Path:
    return resolve_project_root() / "config"


def _legacy_files() -> list[Path]:
    return sorted(
        p
        for p in legacy_dir().glob("comfyui_*.json")
        if p.is_file() and not p.name.endswith(".example.json")
    )


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(resolve_project_root()).as_posix()


def slugify_name(raw: str) -> str:
    """Turn an uploaded filename into a safe library name ending in .json."""
    stem = Path(str(raw or "").strip()).name
    if stem.lower().endswith(".json"):
        stem = stem[:-5]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")[:90]
    return f"{stem or 'workflow'}.json"


def find_workflow(name: str) -> Path | None:
    """Resolve a library or legacy workflow by bare file name; None if unknown or unsafe."""
    if not NAME_RE.match(name or ""):
        return None
    for base in (library_dir(), legacy_dir()):
        candidate = (base / name).resolve()
        if candidate.parent != base.resolve() or not candidate.is_file():
            continue
        if base == legacy_dir() and not (
            name.startswith("comfyui_") and not name.endswith(".example.json")
        ):
            continue
        return candidate
    return None


def parse_workflow(text: str) -> dict[str, Any]:
    """Parse and check a ComfyUI *API-format* workflow; raises ValueError with a reason."""
    if len(text.encode("utf-8")) > MAX_WORKFLOW_BYTES:
        raise ValueError("workflow_too_large")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid_json: {e.msg} (line {e.lineno})") from None
    if isinstance(data, dict) and "nodes" in data and "links" in data:
        raise ValueError(
            "ui_format_workflow: this is the editor graph. In ComfyUI use "
            "Workflow → Export (API) and upload that file instead."
        )
    if not isinstance(data, dict):
        raise ValueError("not_api_workflow: expected an object of node_id → node")
    # "_comment"-style keys are notes; the ComfyUI client strips them before queueing.
    if not any(not str(k).startswith("_") for k in data):
        raise ValueError("not_api_workflow: no nodes")
    for node_id, node in data.items():
        if str(node_id).startswith("_"):
            continue
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str):
            raise ValueError(f"not_api_workflow: node {node_id!r} has no class_type")
        if not isinstance(node.get("inputs", {}), dict):
            raise ValueError(f"not_api_workflow: node {node_id!r} inputs must be an object")
    return data


def analyze_workflow(data: dict[str, Any]) -> dict[str, Any]:
    """What the server needs to know to use a workflow: prompt, output and loader nodes."""
    nodes = []
    prompt_nodes = []
    output_nodes = []
    checkpoint_loaders = []
    for node_id, node in data.items():
        if str(node_id).startswith("_"):
            continue
        cls = node.get("class_type", "")
        title = ((node.get("_meta") or {}).get("title")) or cls
        inputs = node.get("inputs") or {}
        nodes.append({"id": str(node_id), "class_type": cls, "title": title})
        # The server writes the prompt into inputs["text"]; a linked input (a list)
        # would be overwritten, so only literal strings are usable.
        if isinstance(inputs.get("text"), str):
            prompt_nodes.append({"id": str(node_id), "class_type": cls, "title": title})
        if cls in ("SaveImage", "PreviewImage") or cls.startswith("SaveImage"):
            output_nodes.append({"id": str(node_id), "class_type": cls, "title": title})
        if cls == "CheckpointLoaderSimple":
            checkpoint_loaders.append({"id": str(node_id), "ckpt_name": inputs.get("ckpt_name")})

    def _pick_prompt() -> str | None:
        for n in prompt_nodes:
            t = n["title"].lower()
            if "positive" in t and "negative" not in t:
                return n["id"]
        encoders = [n for n in prompt_nodes if "CLIPTextEncode" in n["class_type"]]
        non_negative = [n for n in encoders if "negative" not in n["title"].lower()]
        if len(non_negative) == 1:
            return non_negative[0]["id"]
        return prompt_nodes[0]["id"] if len(prompt_nodes) == 1 else None

    saves = [n for n in output_nodes if n["class_type"].startswith("SaveImage")]
    return {
        "node_count": len(nodes),
        "nodes": sorted(nodes, key=lambda n: (len(n["id"]), n["id"])),
        "prompt_nodes": prompt_nodes,
        "output_nodes": output_nodes,
        "checkpoint_loaders": checkpoint_loaders,
        "suggested_prompt_node_id": _pick_prompt(),
        "suggested_output_node_id": (saves or output_nodes)[0]["id"]
        if len(saves or output_nodes) == 1
        else None,
    }


def _usage(path: Path, comfy_cfg) -> list[str]:
    used = []
    resolved = path.resolve()
    for role, attr in (("portrait", "workflow_path"), ("area", "area_workflow_path")):
        configured = (getattr(comfy_cfg, attr, "") or "").strip()
        if not configured:
            continue
        p = Path(configured)
        p = p if p.is_absolute() else resolve_project_root() / p
        if p.resolve() == resolved:
            used.append(role)
    return used


def _summary(path: Path, comfy_cfg) -> dict[str, Any]:
    st = path.stat()
    item: dict[str, Any] = {
        "name": path.name,
        "path": relative_path(path),
        "source": "library" if path.parent.resolve() == library_dir().resolve() else "legacy",
        "size_bytes": st.st_size,
        "modified_at": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
        "in_use_as": _usage(path, comfy_cfg),
    }
    try:
        analysis = analyze_workflow(parse_workflow(path.read_text(encoding="utf-8")))
        item.update(
            valid=True,
            error=None,
            node_count=analysis["node_count"],
            prompt_node_count=len(analysis["prompt_nodes"]),
            output_node_count=len(analysis["output_nodes"]),
        )
    except (ValueError, OSError) as e:
        item.update(
            valid=False, error=str(e), node_count=0, prompt_node_count=0, output_node_count=0
        )
    return item


def list_workflows(comfy_cfg) -> list[dict[str, Any]]:
    lib = library_dir()
    files = sorted(lib.glob("*.json")) if lib.is_dir() else []
    return [_summary(p, comfy_cfg) for p in [*files, *_legacy_files()]]


def workflow_detail(name: str, comfy_cfg) -> dict[str, Any] | None:
    path = find_workflow(name)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8")
    detail = _summary(path, comfy_cfg)
    detail["content"] = text
    try:
        detail["analysis"] = analyze_workflow(parse_workflow(text))
    except ValueError:
        detail["analysis"] = None
    return detail


def save_workflow(name: str, text: str, *, overwrite: bool = False) -> Path:
    """Validate and atomically write a workflow into the library. Raises ValueError."""
    if not NAME_RE.match(name or ""):
        raise ValueError("invalid_name")
    data = parse_workflow(text)
    lib = library_dir()
    lib.mkdir(parents=True, exist_ok=True)
    target = lib / name
    if target.exists() and not overwrite:
        raise ValueError("name_taken")
    pretty = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=lib, prefix=".upload-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(pretty)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return target


def delete_workflow(name: str, comfy_cfg) -> None:
    path = find_workflow(name)
    if path is None:
        raise FileNotFoundError(name)
    if path.parent.resolve() != library_dir().resolve():
        raise ValueError("legacy_workflow_protected")
    in_use = _usage(path, comfy_cfg)
    if in_use:
        raise ValueError(f"workflow_in_use:{','.join(in_use)}")
    path.unlink()


def assignment_patch(
    name: str, role: str, prompt_node_id: str | None, output_node_id: str | None
) -> dict[str, str]:
    """Settings patch to point a role at a workflow, after checking the node ids. Raises ValueError."""
    if role not in ROLES:
        raise ValueError("invalid_role")
    path = find_workflow(name)
    if path is None:
        raise FileNotFoundError(name)
    analysis = analyze_workflow(parse_workflow(path.read_text(encoding="utf-8")))
    prompt_id = (prompt_node_id or analysis["suggested_prompt_node_id"] or "").strip()
    output_id = (output_node_id or analysis["suggested_output_node_id"] or "").strip()
    if prompt_id not in {n["id"] for n in analysis["prompt_nodes"]}:
        raise ValueError("prompt_node_required: pick a node with a literal text input")
    if output_id not in {n["id"] for n in analysis["output_nodes"]}:
        raise ValueError("output_node_required: pick a SaveImage/PreviewImage node")
    rel = relative_path(path)
    if role == "portrait":
        return {
            "workflow_path": rel,
            "positive_prompt_node_id": prompt_id,
            "output_node_id": output_id,
        }
    return {
        "area_workflow_path": rel,
        "area_positive_prompt_node_id": prompt_id,
        "area_output_node_id": output_id,
    }
