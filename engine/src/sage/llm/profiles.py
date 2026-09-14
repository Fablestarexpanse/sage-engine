"""Named LLM profiles: a secondary, live-reconfigurable LLM next to the narration client.

The ``agents_llm`` config section (config/agents_llm.toml) describes one: an OpenAI-compatible
endpoint or an in-process GGUF model. Plugins that generate character speech or plans ask for it
with ``api.ai.profile("agents_llm")``; the admin panel edits it live. An embedded model is shared
with narration so only one copy is loaded.
"""

from __future__ import annotations

import time
from typing import Any

from sage.llm.client import LLMClient, LLMGenerationError

BACKENDS = ("lm_studio", "ollama", "embedded")


def _is_embedded(config: Any) -> bool:
    return (config.primary_backend or "").lower().strip() == "embedded"


class LLMProfile:
    def __init__(self, server: Any, section: str = "agents_llm"):
        self.server = server
        self.section = section
        self.client = self._build(self.config)

    @property
    def config(self) -> Any:
        return getattr(self.server.config, self.section)

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    def _build(self, config: Any) -> Any:
        if _is_embedded(config):
            getter = getattr(self.server, "embedded_llm", None)
            if callable(getter):
                shared = getter()
                shared.reconfigure(config)
                return shared
            from sage.llm.embedded import EmbeddedLLM

            return EmbeddedLLM(config)
        return LLMClient(config)

    def reconfigure(self, config: Any) -> None:
        """Apply new settings live (admin panel save)."""
        setattr(self.server.config, self.section, config)
        if _is_embedded(config) != (type(self.client).__name__ == "EmbeddedLLM"):
            self.client = self._build(config)
        else:
            self.client.reconfigure(config)

    async def generate(self, prompt: str, *, system_prompt: str, max_tokens: int) -> str:
        """Generate or raise LLMGenerationError (callers fall back to rules)."""
        return await self.client.generate_or_raise(
            prompt, system_prompt=system_prompt, max_tokens=max_tokens
        )

    def status(self) -> dict[str, Any]:
        cfg = self.config
        base = {
            "enabled": bool(cfg.enabled),
            "backend": cfg.primary_backend,
            "chat_model": cfg.chat_model,
            "lm_studio_url": cfg.lm_studio_url,
            "ollama_url": cfg.ollama_url,
            "model_path": cfg.model_path,
            "temperature": cfg.temperature,
            "timeout_seconds": cfg.timeout_seconds,
        }
        if hasattr(self.client, "status"):
            base["embedded"] = self.client.status()
        return base

    async def probe(self, prompt: str) -> dict[str, Any]:
        """One-shot generation proving the profile answers."""
        started = time.time()
        try:
            reply = await self.generate(
                prompt, system_prompt="Output only the spoken line.", max_tokens=60
            )
            return {"ok": True, "reply": reply[:300], "latency_s": round(time.time() - started, 2)}
        except LLMGenerationError as exc:
            return {"ok": False, "error": str(exc), "latency_s": round(time.time() - started, 2)}
