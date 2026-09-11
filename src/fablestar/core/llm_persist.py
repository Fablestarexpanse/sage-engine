"""Persist LLM settings to config/llm.toml for restarts."""

from __future__ import annotations

import json
from pathlib import Path

from fablestar.core.config import LLMConfig


def _toml_string(s: str) -> str:
    return json.dumps(s)


def save_llm_toml(llm: LLMConfig, path: Path | None = None) -> Path:
    target = path or Path("config/llm.toml")
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Auto-written by Fablestar Nexus (admin UI). Safe to edit by hand.",
        f"primary_backend = {_toml_string(llm.primary_backend)}",
        f"lm_studio_url = {_toml_string(llm.lm_studio_url)}",
        f"lm_studio_key = {_toml_string(llm.lm_studio_key)}",
        f"ollama_url = {_toml_string(llm.ollama_url)}",
        f"timeout_seconds = {float(llm.timeout_seconds)}",
        f"cache_ttl = {int(llm.cache_ttl)}",
        f"chat_model = {_toml_string(llm.chat_model)}",
        f"temperature = {float(llm.temperature)}",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
