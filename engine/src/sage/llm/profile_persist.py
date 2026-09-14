"""Persist agent-brain LLM settings to config/agents_llm.toml for restarts."""

from __future__ import annotations

from pathlib import Path

from sage.core.config import AgentsLLMConfig
from sage.core.toml_persist import atomic_write_toml
from sage.core.toml_persist import toml_str as _toml_string


def save_agents_llm_toml(cfg: AgentsLLMConfig, path: Path | None = None) -> Path:
    target = path or Path("config/agents_llm.toml")
    lines = [
        "# Auto-written by SAGE Nexus (admin Agents panel). Safe to edit by hand.",
        f"enabled = {'true' if cfg.enabled else 'false'}",
        f"primary_backend = {_toml_string(cfg.primary_backend)}",
        f"lm_studio_url = {_toml_string(cfg.lm_studio_url)}",
        f"ollama_url = {_toml_string(cfg.ollama_url)}",
        f"chat_model = {_toml_string(cfg.chat_model)}",
        f"model_path = {_toml_string(cfg.model_path)}",
        f"embedded_ctx = {int(cfg.embedded_ctx)}",
        f"temperature = {float(cfg.temperature)}",
        f"timeout_seconds = {float(cfg.timeout_seconds)}",
        "",
    ]
    return atomic_write_toml(target, lines)
