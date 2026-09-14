"""Persist LLM settings to config/llm.toml for restarts."""

from __future__ import annotations

from pathlib import Path

from sage.core.config import LLMConfig
from sage.core.toml_persist import atomic_write_toml
from sage.core.toml_persist import toml_str as _toml_string


def save_llm_toml(llm: LLMConfig, path: Path | None = None) -> Path:
    target = path or Path("config/llm.toml")
    lines = [
        "# Auto-written by SAGE Nexus (admin UI). Safe to edit by hand.",
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
    return atomic_write_toml(target, lines)
