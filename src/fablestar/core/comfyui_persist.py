"""Persist ComfyUI settings to config/comfyui.toml for restarts."""

from __future__ import annotations

from pathlib import Path

from fablestar.core.config import ComfyUIConfig
from fablestar.core.toml_persist import toml_str as _toml_str


def save_comfyui_toml(cfg: ComfyUIConfig, path: Path | None = None) -> Path:
    target = path or Path("config/comfyui.toml")
    lines = [
        "# Auto-written by Fablestar Nexus (admin UI). Safe to edit by hand.",
        f"enabled = {str(cfg.enabled).lower()}",
        f"base_url = {_toml_str(cfg.base_url)}",
        "",
        f"workflow_path = {_toml_str(cfg.workflow_path)}",
        f"positive_prompt_node_id = {_toml_str(cfg.positive_prompt_node_id)}",
        f"output_node_id = {_toml_str(cfg.output_node_id)}",
        "",
        f"area_workflow_path = {_toml_str(cfg.area_workflow_path)}",
        f"area_positive_prompt_node_id = {_toml_str(cfg.area_positive_prompt_node_id)}",
        f"area_output_node_id = {_toml_str(cfg.area_output_node_id)}",
        "",
        f"checkpoint_name = {_toml_str(cfg.checkpoint_name)}",
        f"timeout_seconds = {float(cfg.timeout_seconds)}",
        f"poll_interval_seconds = {float(cfg.poll_interval_seconds)}",
        "",
        f"economy_enabled = {str(cfg.economy_enabled).lower()}",
        f"starting_echo_credits = {int(cfg.starting_echo_credits)}",
        f"portrait_generation_cost = {int(cfg.portrait_generation_cost)}",
        f"area_generation_cost = {int(cfg.area_generation_cost)}",
        f"character_create_portrait_cost = {int(cfg.character_create_portrait_cost)}",
        f"currency_display_name = {_toml_str(cfg.currency_display_name)}",
        f"pixels_per_usd = {int(cfg.pixels_per_usd)}",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
