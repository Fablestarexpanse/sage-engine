"""Minimal ComfyUI HTTP client: queue prompt, poll history, download PNG."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Any

import httpx

from fablestar.core.config import ComfyUIConfig, resolve_config_asset_path

logger = logging.getLogger(__name__)


def _load_workflow(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("workflow_not_object")
    # Strip comment-only keys
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


def _strip_node_meta_for_api(workflow: dict[str, Any]) -> None:
    """Remove per-node _meta (UI metadata); ComfyUI /prompt often rejects unknown node keys."""
    for node in workflow.values():
        if isinstance(node, dict) and "_meta" in node:
            del node["_meta"]


def _inject_positive_prompt(workflow: dict[str, Any], node_id: str, text: str) -> None:
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        raise ValueError(f"missing_node:{node_id}")
    inputs = node.get("inputs")
    if not isinstance(inputs, dict) or "text" not in inputs:
        raise ValueError(f"node_has_no_text_input:{node_id}")
    inputs["text"] = text


def _random_comfy_seed() -> int:
    return secrets.randbelow(2**32)


def _scramble_seeds_in_workflow(workflow: dict[str, Any]) -> None:
    """New random image each run (workflow JSON often ships with fixed KSampler seeds)."""
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or "seed" not in inputs:
            continue
        v = inputs["seed"]
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            inputs["seed"] = _random_comfy_seed()
        elif isinstance(v, float):
            inputs["seed"] = _random_comfy_seed()


def _get_history_entry(history: Any, prompt_id: str) -> dict[str, Any] | None:
    if not isinstance(history, dict) or not history:
        return None
    if prompt_id in history:
        e = history[prompt_id]
        return e if isinstance(e, dict) else None
    for k, v in history.items():
        if str(k) == str(prompt_id) and isinstance(v, dict):
            return v
    return None


def _history_entry_failed(entry: dict[str, Any]) -> str | None:
    st = entry.get("status")
    if not isinstance(st, dict):
        return None
    s = st.get("status_str") or st.get("status")
    if str(s).lower() in ("error", "failed"):
        parts: list[str] = []
        for key in ("message", "error", "detail"):
            m = st.get(key)
            if m and str(m) not in parts:
                parts.append(str(m))
        msgs = st.get("messages")
        if isinstance(msgs, list):
            for m in msgs:
                if isinstance(m, list | tuple) and len(m) >= 2:
                    parts.append(str(m[1]))
                elif isinstance(m, str):
                    parts.append(m)
        return " | ".join(parts) if parts else str(s)
    return None


def _pick_image_output_block(
    outputs: dict[str, Any], output_node_id: str
) -> tuple[dict[str, Any], str] | None:
    """Return (block, node_id) for SaveImage / image output; prefer configured node id."""
    pref = outputs.get(output_node_id)
    if isinstance(pref, dict) and pref.get("images"):
        return pref, output_node_id
    best_n = -1
    best_block: dict[str, Any] | None = None
    best_id = ""
    for nid, block in outputs.items():
        if not isinstance(block, dict):
            continue
        if not block.get("images"):
            continue
        try:
            n = int(str(nid))
        except ValueError:
            n = 0
        if n > best_n:
            best_n = n
            best_block = block
            best_id = str(nid)
    if best_block is not None:
        return best_block, best_id
    return None


def _apply_checkpoint_override(workflow: dict[str, Any], ckpt_name: str) -> None:
    name = (ckpt_name or "").strip()
    if not name:
        return
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "CheckpointLoaderSimple":
            continue
        inputs = node.get("inputs")
        if isinstance(inputs, dict):
            inputs["ckpt_name"] = name


def _workflow_has_checkpoint_loader_simple(workflow: dict[str, Any]) -> bool:
    for v in workflow.values():
        if isinstance(v, dict) and v.get("class_type") == "CheckpointLoaderSimple":
            return True
    return False


def _flatten_ckpt_name_widget(v: Any) -> list[str]:
    """Turn ComfyUI widget value for ckpt_name into a list of filename strings."""
    if not isinstance(v, list) or not v:
        return []
    head = v[0]
    if isinstance(head, list):
        return [str(x) for x in head if isinstance(x, str) and str(x).strip()]
    if isinstance(head, str):
        return [str(x) for x in v if isinstance(x, str) and str(x).strip()]
    return []


def _longest_ckpt_name_list_in_json(root: Any) -> list[str]:
    """
    ComfyUI versions differ: ckpt_name may live under input.required, optional, etc.
    Scan the whole JSON tree and use the longest ckpt_name option list (the real checkpoint list).
    """
    best: list[str] = []

    def walk(x: Any) -> None:
        nonlocal best
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "ckpt_name":
                    opts = _flatten_ckpt_name_widget(v)
                    if len(opts) > len(best):
                        best = opts
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(root)
    return best


async def _list_checkpoints_from_comfy(client: httpx.AsyncClient, base: str) -> list[str]:
    """Fetch checkpoint filenames ComfyUI accepts (via object_info)."""
    urls = (f"{base}/object_info/CheckpointLoaderSimple", f"{base}/object_info")
    best: list[str] = []
    for url in urls:
        try:
            r = await client.get(url)
            if r.status_code != 200:
                logger.debug("ComfyUI checkpoint list: %s HTTP %s", url, r.status_code)
                continue
            payload = r.json()
            found = _longest_ckpt_name_list_in_json(payload)
            if len(found) > len(best):
                best = found
        except Exception as e:
            logger.debug("ComfyUI checkpoint list: GET %s failed: %s", url, e)
    if not best:
        for path in ("/models/checkpoints", "/models"):
            try:
                r = await client.get(f"{base}{path}")
                if r.status_code != 200:
                    continue
                j = r.json()
                if isinstance(j, list):
                    cand = [str(x) for x in j if str(x).strip()]
                elif isinstance(j, dict):
                    cand = j.get("checkpoints")
                    if not isinstance(cand, list):
                        continue
                    cand = [str(x) for x in cand if str(x).strip()]
                else:
                    continue
                if len(cand) > len(best):
                    best = cand
                    logger.debug("ComfyUI: checkpoint list from GET %s (%s)", path, len(best))
                    break
            except Exception as e:
                logger.debug("ComfyUI checkpoint list: GET %s failed: %s", path, e)
    if best:
        logger.debug("ComfyUI: resolved %s checkpoint name(s)", len(best))
    return best


def _resolve_checkpoint_for_workflow(
    workflow: dict[str, Any],
    cfg: ComfyUIConfig,
    available: list[str],
) -> None:
    """
    Set ckpt_name on every CheckpointLoaderSimple node.
    - Prefer comfyui.toml checkpoint_name if it appears in `available`.
    - Else if workflow value is missing or not in `available`, use available[0].
    """
    if not _workflow_has_checkpoint_loader_simple(workflow):
        return
    toml = (cfg.checkpoint_name or "").strip()
    if not available:
        if toml:
            _apply_checkpoint_override(workflow, toml)
            logger.warning(
                "ComfyUI: could not list checkpoints from object_info; using checkpoint_name from config: %r",
                toml,
            )
        else:
            logger.warning(
                "ComfyUI: could not list checkpoints (is ComfyUI reachable at %s?). "
                "Set checkpoint_name in comfyui.toml to a real filename.",
                cfg.base_url,
            )
        return

    chosen = toml if toml and toml in available else available[0]
    if toml and toml not in available:
        logger.warning(
            "ComfyUI: checkpoint_name %r not in host list (%s models); using %r instead",
            toml,
            len(available),
            chosen,
        )
    elif not toml:
        logger.info(
            "ComfyUI: using checkpoint %r (set checkpoint_name in comfyui.toml to pin another)",
            chosen,
        )
    _apply_checkpoint_override(workflow, chosen)


def _comfy_error_detail(response: httpx.Response) -> str:
    """Extract ComfyUI /prompt error JSON into a short string for logs and API detail."""
    text = (response.text or "").strip()
    if not text:
        return "(empty response body)"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[:3000]
    parts: list[str] = []
    err = data.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if msg:
            parts.append(str(msg))
        typ = err.get("type")
        if typ and typ != msg:
            parts.append(f"type={typ}")
        det = err.get("details")
        if det and str(det) not in str(msg or ""):
            parts.append(str(det))
    ne = data.get("node_errors")
    if isinstance(ne, dict) and ne:
        snippet = json.dumps(ne, ensure_ascii=False)
        if len(snippet) > 2800:
            snippet = snippet[:2800] + "…"
        parts.append(f"node_errors={snippet}")
    return " | ".join(parts) if parts else text[:3000]


def _resolve_workflow(cfg: ComfyUIConfig, kind: str) -> tuple[Path, str, str]:
    """Return (workflow_path, positive_prompt_node_id, output_node_id). kind is portrait | area."""
    k = (kind or "portrait").lower().strip()
    if k == "area":
        wp = (cfg.area_workflow_path or "").strip() or cfg.workflow_path
        pid = (cfg.area_positive_prompt_node_id or "").strip() or cfg.positive_prompt_node_id
        oid = (cfg.area_output_node_id or "").strip() or cfg.output_node_id
    else:
        wp = cfg.workflow_path
        pid = cfg.positive_prompt_node_id
        oid = cfg.output_node_id
    return resolve_config_asset_path(wp), pid, oid


async def generate_comfy_png(
    cfg: ComfyUIConfig,
    user_prompt: str,
    kind: str = "portrait",
) -> tuple[bytes, str]:
    """
    Run ComfyUI once; return (png_bytes, empty_error_string).
    kind: "portrait" | "area"
    """
    if not cfg.enabled:
        raise RuntimeError("comfyui_disabled")

    wf_path, pos_node, output_node_id = _resolve_workflow(cfg, kind)
    if not wf_path.is_file():
        raise FileNotFoundError(f"workflow_missing:{wf_path}")
    logger.info(
        "ComfyUI run: kind=%s file=%s positive_node=%s output_node=%s",
        kind,
        wf_path,
        pos_node,
        output_node_id,
    )

    user_prompt = (user_prompt or "").strip()
    if len(user_prompt) < 3:
        raise ValueError("prompt_too_short")

    workflow = _load_workflow(wf_path)
    _strip_node_meta_for_api(workflow)
    _inject_positive_prompt(workflow, pos_node, user_prompt)
    _scramble_seeds_in_workflow(workflow)

    base = cfg.base_url.rstrip("/")
    client_id = str(uuid.uuid4())
    timeout = httpx.Timeout(cfg.timeout_seconds + 10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        available = await _list_checkpoints_from_comfy(client, base)
        _resolve_checkpoint_for_workflow(workflow, cfg, available)

        pr = await client.post(f"{base}/prompt", json={"prompt": workflow, "client_id": client_id})
        if pr.status_code >= 400:
            detail = _comfy_error_detail(pr)
            raise RuntimeError(f"ComfyUI /prompt HTTP {pr.status_code}: {detail}")
        body = pr.json()
        prompt_id = body.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"comfyui_no_prompt_id:{body}")
        prompt_id = str(prompt_id)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + cfg.timeout_seconds
        last_outputs: dict[str, Any] = {}
        picked: tuple[dict[str, Any], str] | None = None
        while loop.time() < deadline:
            try:
                hr = await client.get(f"{base}/history/{prompt_id}")
            except httpx.RequestError:
                continue
            if hr.status_code == 404:
                continue
            if hr.status_code != 200:
                continue
            try:
                history = hr.json()
            except json.JSONDecodeError:
                continue
            entry = _get_history_entry(history, prompt_id)
            if not isinstance(entry, dict):
                continue
            err = _history_entry_failed(entry)
            if err:
                raise RuntimeError(f"comfyui_prompt_failed:{err}")
            outs = entry.get("outputs")
            if isinstance(outs, dict):
                last_outputs = outs
            picked = _pick_image_output_block(last_outputs, output_node_id)
            if picked:
                break
            await asyncio.sleep(cfg.poll_interval_seconds)
        else:
            picked = _pick_image_output_block(last_outputs, output_node_id)
            if not picked:
                raise TimeoutError("comfyui_timeout")

        assert picked is not None
        out_block, used_node = picked
        if not isinstance(out_block, dict):
            raise RuntimeError(f"comfyui_no_output_node:{output_node_id}")
        images = out_block.get("images") or []
        if not images:
            raise RuntimeError("comfyui_no_images")
        if used_node != output_node_id:
            logger.warning(
                "ComfyUI: expected images on node %r; used node %r (check output_node_id in comfyui.toml)",
                output_node_id,
                used_node,
            )

        img0 = images[0]
        filename = img0.get("filename")
        subfolder = img0.get("subfolder") or ""
        typ = img0.get("type") or "output"
        if not filename:
            raise RuntimeError("comfyui_no_filename")

        params = {"filename": filename, "type": typ}
        if subfolder:
            params["subfolder"] = subfolder
        vr = await client.get(f"{base}/view", params=params)
        vr.raise_for_status()
        data = vr.content
        if not data:
            raise RuntimeError("comfyui_empty_image")
        return data, ""


async def generate_portrait_png(
    cfg: ComfyUIConfig,
    appearance_prompt: str,
) -> tuple[bytes, str]:
    """Portrait workflow (backwards-compatible name)."""
    return await generate_comfy_png(cfg, appearance_prompt, kind="portrait")


def workflow_template_copy_destination() -> Path:
    """Hint path for operators copying the example workflow."""
    return Path("config/comfyui_portrait_workflow.json")
