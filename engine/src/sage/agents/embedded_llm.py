"""
EmbeddedLLM — in-process GGUF inference for agent brains (llama-cpp-python).

Same generate_or_raise contract as LLMClient, so AgentBrain can swap between
an external endpoint and this without caring. Inference is CPU/GPU work, so
calls run in a worker thread behind a lock (Llama instances are not
thread-safe); the tick loop never blocks.
"""

import asyncio
import logging
import threading
import time
from pathlib import Path

from sage.core.config import AgentsLLMConfig
from sage.llm.client import LLMGenerationError

logger = logging.getLogger(__name__)

BREAKER_COOLDOWN_S = 30.0


class EmbeddedLLM:
    def __init__(self, config: AgentsLLMConfig):
        self.config = config
        self._llama = None
        self._lock = threading.Lock()
        self._breaker_open_until = 0.0
        self._load_error: str | None = None

    # -- lifecycle ------------------------------------------------------

    def reconfigure(self, config: AgentsLLMConfig) -> None:
        with self._lock:
            reload_needed = (
                config.model_path != self.config.model_path
                or config.embedded_ctx != self.config.embedded_ctx
            )
            self.config = config
            if reload_needed:
                self._llama = None
                self._load_error = None
                self._breaker_open_until = 0.0

    def status(self) -> dict:
        path = Path(self.config.model_path) if self.config.model_path else None
        return {
            "backend": "embedded",
            "model_path": self.config.model_path,
            "model_file_exists": bool(path and path.is_file()),
            "loaded": self._llama is not None,
            "load_error": self._load_error,
        }

    def _ensure_loaded(self):
        """Called under the lock, in the worker thread."""
        if self._llama is not None:
            return self._llama
        if self._load_error:
            raise LLMGenerationError(f"embedded model previously failed: {self._load_error}")
        path = Path(self.config.model_path)
        if not self.config.model_path or not path.is_file():
            raise LLMGenerationError(f"embedded model file not found: {self.config.model_path!r}")
        try:
            from llama_cpp import Llama

            logger.info("Embedded LLM loading %s ...", path.name)
            started = time.monotonic()
            self._llama = Llama(
                model_path=str(path),
                n_ctx=int(self.config.embedded_ctx),
                n_gpu_layers=-1,  # use GPU when the wheel supports it; no-op on CPU builds
                verbose=False,
            )
            logger.info("Embedded LLM ready (%s, %.1fs)", path.name, time.monotonic() - started)
        except LLMGenerationError:
            raise
        except Exception as exc:
            self._load_error = str(exc)
            raise LLMGenerationError(f"embedded model load failed: {exc}") from exc
        return self._llama

    # -- generation -----------------------------------------------------

    def _generate_sync(self, prompt: str, system_prompt: str, max_tokens: int) -> str:
        with self._lock:
            llama = self._ensure_loaded()
            result = llama.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=float(self.config.temperature),
                max_tokens=max_tokens,
            )
        text = (result["choices"][0]["message"]["content"] or "").strip()
        if not text:
            raise LLMGenerationError("embedded model returned an empty response")
        return text

    async def generate_or_raise(
        self,
        prompt: str,
        system_prompt: str = "You are a master storyteller for a dark sci-fi MUD.",
        max_tokens: int = 250,
    ) -> str:
        now = time.monotonic()
        if now < self._breaker_open_until:
            raise LLMGenerationError(
                f"embedded LLM circuit open for {self._breaker_open_until - now:.0f}s more"
            )
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._generate_sync, prompt, system_prompt, max_tokens),
                timeout=max(5.0, float(self.config.timeout_seconds) * 4),
            )
        except LLMGenerationError as exc:
            # Missing/broken model: open the breaker so ticks stay cheap.
            self._breaker_open_until = time.monotonic() + BREAKER_COOLDOWN_S
            raise exc
        except TimeoutError as exc:
            self._breaker_open_until = time.monotonic() + BREAKER_COOLDOWN_S
            raise LLMGenerationError("embedded generation timed out") from exc
        except Exception as exc:
            self._breaker_open_until = time.monotonic() + BREAKER_COOLDOWN_S
            raise LLMGenerationError(f"embedded generation failed: {exc}") from exc
