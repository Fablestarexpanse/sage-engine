"""LLMClient — async HTTP client for OpenAI-compatible endpoints (LM Studio, Ollama)."""

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from openai import AsyncOpenAI

from sage.core.config import LLMConfig
from sage.core.openai_util import normalize_openai_compatible_base

logger = logging.getLogger(__name__)


# Seconds of fast-fail after a connection failure/timeout; a success resets it.
BREAKER_COOLDOWN_S = 30.0


class LLMGenerationError(Exception):
    """LLM generation failed (timeout, transport error, or empty response)."""


def chat_model_is_auto(chat_model: str, model_ids: list[str], backend: str) -> bool:
    """True when Nexus should pick the model from the server list (not a fixed id)."""
    raw = (chat_model or "").strip()
    s = raw.lower()
    if s in ("", "auto", "*"):
        return True
    b = (backend or "lm_studio").lower().strip()
    # Legacy default: LM Studio rarely exposes id "local-model"; treat as auto when absent.
    if b == "lm_studio" and raw == "local-model" and "local-model" not in model_ids:
        return True
    return False


def infer_detected_chat_model(
    models: list[dict[str, Any]],
    configured_id: str,
    backend: str,
    connected: bool,
) -> tuple[str | None, str | None]:
    """
    Best-effort id of the model the OpenAI-compatible server is exposing.

    LM Studio's /v1/models list is typically the loaded model(s). Ollama lists
    all pulled models, so we only infer when the configured id is present or
    exactly one model is listed.
    """
    if not connected or not models:
        return None, None
    ids = [str(m["id"]) for m in models if m.get("id")]
    if not ids:
        return None, None
    cfg = (configured_id or "").strip()
    cfg_lower = cfg.lower()
    prefer_auto = cfg_lower in ("", "auto", "*")
    b = (backend or "lm_studio").lower().strip()

    if prefer_auto:
        if b == "lm_studio" and len(ids) == 1:
            return ids[0], "loaded"
        return ids[0], "listed"

    if b == "lm_studio":
        if len(ids) == 1:
            return ids[0], "loaded"
        if cfg in ids:
            return cfg, "listed"
        return ids[0], "listed"

    if cfg in ids:
        return cfg, "listed"
    if len(ids) == 1:
        return ids[0], "listed"
    return None, None


class LLMClient:
    """
    Client for interacting with LLM backends.
    Primary focus: LM Studio and Ollama (OpenAI-compatible /v1 API).
    """

    #: How long to reuse GET /v1/models probe results (reduces LM Studio log spam / load).
    _probe_cache_ttl_s: float = 60.0

    def __init__(self, config: LLMConfig):
        # The running world's narration voice (ai/style.yaml system_prompt); set by the server.
        self.default_system_prompt = "You narrate for a text game."
        self.config = config
        self.client = self._build_openai_client()
        self.timeout = config.timeout_seconds
        self._probe_lock = asyncio.Lock()
        self._status_cache: dict[str, Any] | None = None
        self._status_cache_at: float = 0.0
        # Circuit breaker: after a connection failure, fast-fail generation for
        # this many seconds instead of paying connect-retry latency per command.
        self._breaker_open_until: float = 0.0
        # When primary_backend == "embedded", this callable returns the shared
        # in-process EmbeddedLLM (set by the server; one GGUF serves narration
        # and agent brains alike).
        self.embedded_getter = None

    def _openai_base_url(self) -> str:
        backend = (self.config.primary_backend or "lm_studio").lower().strip()
        if backend == "ollama":
            return normalize_openai_compatible_base(self.config.ollama_url)
        return normalize_openai_compatible_base(self.config.lm_studio_url)

    def _api_key(self) -> str:
        return self.config.lm_studio_key or "not-needed"

    def _build_openai_client(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=self._openai_base_url(),
            api_key=self._api_key(),
        )

    def reconfigure(self, config: LLMConfig) -> None:
        """Apply new LLM settings (same instance, new HTTP client)."""
        self.config = config
        self.client = self._build_openai_client()
        self.timeout = config.timeout_seconds
        self._status_cache = None
        self._status_cache_at = 0.0
        self._breaker_open_until = 0.0
        logger.info(
            "LLM client reconfigured: backend=%s base=%s model=%s",
            config.primary_backend,
            self._openai_base_url(),
            config.chat_model,
        )

    async def effective_chat_model(self) -> str:
        """Model id sent to the OpenAI-compatible API (resolves auto / legacy local-model)."""
        st = await self.status_dict()
        cfg = (self.config.chat_model or "").strip()
        backend = (self.config.primary_backend or "lm_studio").lower().strip()
        models = st.get("models") or []
        ids = [str(m["id"]) for m in models if m.get("id")]
        if chat_model_is_auto(cfg, ids, backend):
            d, _ = infer_detected_chat_model(models, "auto", backend, bool(st.get("connected")))
            if d:
                return d
            return cfg or "local-model"
        if cfg:
            return cfg
        d, _ = infer_detected_chat_model(models, "auto", backend, bool(st.get("connected")))
        return d or "local-model"

    async def probe_connection(
        self, list_timeout: float = 3.0
    ) -> tuple[bool, float | None, str | None, list[dict[str, Any]], str | None]:
        """
        Ping the OpenAI-compatible server (models list).
        Uses an explicit GET {base}/models via httpx so the URL is always /v1/models
        (LM Studio logs "GET /models" when the HTTP path is wrong: /models at server root).
        Returns: ok, latency_ms, error_message, models[{id}], server_version_hint
        """
        root = self._openai_base_url().rstrip("/")
        list_url = f"{root}/models"
        t0 = time.perf_counter()
        headers: dict[str, str] = {}
        key = self._api_key()
        if key and key.strip() and key != "not-needed":
            headers["Authorization"] = f"Bearer {key.strip()}"

        try:
            async with httpx.AsyncClient(timeout=list_timeout) as http:
                resp = await http.get(list_url, headers=headers)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code >= 400:
                return (
                    False,
                    latency_ms,
                    f"HTTP {resp.status_code} from {list_url}: {resp.text[:200]}",
                    [],
                    None,
                )
            payload = resp.json()
            models: list[dict[str, Any]] = []
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                return False, latency_ms, "Unexpected /models JSON (missing data[])", [], None
            for m in data:
                if not isinstance(m, dict):
                    continue
                mid = m.get("id")
                if mid:
                    models.append({"id": mid})
            return True, latency_ms, None, models, None
        except httpx.TimeoutException:
            return (
                False,
                None,
                f"Timed out after {list_timeout}s (is the server running?)",
                [],
                None,
            )
        except httpx.RequestError as e:
            logger.warning("LLM probe failed: %s", e)
            return False, None, str(e), [], None
        except json.JSONDecodeError as e:
            return False, None, f"Invalid JSON from {list_url}: {e}", [], None

    async def _build_status_dict(self, list_timeout: float) -> dict[str, Any]:
        if (self.config.primary_backend or "").lower().strip() == "embedded":
            embedded = self.embedded_getter() if self.embedded_getter else None
            est = embedded.status() if embedded else {}
            ok = bool(est.get("model_file_exists"))
            model_name = (est.get("model_path") or "").split("/")[-1].split("\\")[-1] or None
            return {
                "connected": ok,
                "latency_ms": None,
                "error": None if ok else "embedded model file not found",
                "primary_backend": "embedded",
                "base_url": "embedded (in-server)",
                "chat_model": model_name,
                "chat_model_auto": False,
                "detected_model": model_name,
                "detected_model_source": "embedded",
                "models_align": True if ok else None,
                "model_known": ok,
                "temperature": self.config.temperature,
                "timeout_seconds": self.config.timeout_seconds,
                "models": [{"id": model_name}] if model_name else [],
                "model_count": 1 if model_name else 0,
                "server_hint": None,
                "cached": False,
            }
        ok, latency_ms, err, models, hint = await self.probe_connection(list_timeout=list_timeout)
        active = self.config.chat_model
        ids = [str(m["id"]) for m in models if m.get("id")]
        backend = self.config.primary_backend
        auto = chat_model_is_auto(active, ids, backend)
        matched = next((m for m in models if m["id"] == active), None)
        detected_id, detected_src = infer_detected_chat_model(
            models, "auto" if auto else active, backend, ok
        )
        if not ok:
            models_align = None
        elif auto:
            models_align = True if detected_id else None
        else:
            models_align = (active in ids) if ids else None
        if auto:
            model_known = bool(detected_id) if models else None
        else:
            model_known = matched is not None if models else None
        return {
            "connected": ok,
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
            "error": err,
            "primary_backend": self.config.primary_backend,
            "base_url": self._openai_base_url(),
            "chat_model": active,
            "chat_model_auto": auto,
            "detected_model": detected_id,
            "detected_model_source": detected_src,
            "models_align": models_align,
            "model_known": model_known,
            "temperature": self.config.temperature,
            "timeout_seconds": self.config.timeout_seconds,
            "models": models[:80],
            "model_count": len(models),
            "server_hint": hint,
            "cached": False,
        }

    async def status_dict(
        self, list_timeout: float = 3.0, *, bypass_cache: bool = False
    ) -> dict[str, Any]:
        """
        Return reachability + model list. Probes GET /v1/models unless a fresh cache exists
        (default TTL 60s) to avoid hammering LM Studio when many admin endpoints poll.
        """
        async with self._probe_lock:
            now = time.monotonic()
            if (
                not bypass_cache
                and self._status_cache is not None
                and (now - self._status_cache_at) < self._probe_cache_ttl_s
            ):
                out = dict(self._status_cache)
                out["cached"] = True
                return out
            fresh = await self._build_status_dict(list_timeout)
            self._status_cache = fresh
            self._status_cache_at = now
            return dict(fresh)

    async def generate_or_raise(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 250,
    ) -> str:
        """
        Generate text from the LLM, raising LLMGenerationError on failure.

        Use this when the caller needs to distinguish real output from failure
        (structured generation, API responses). Narration paths that want a
        graceful fallback catch LLMGenerationError and send nothing.
        """
        system_prompt = system_prompt or self.default_system_prompt
        if (self.config.primary_backend or "").lower().strip() == "embedded":
            embedded = self.embedded_getter() if self.embedded_getter else None
            if embedded is None:
                raise LLMGenerationError("embedded backend selected but not available")
            return await embedded.generate_or_raise(
                prompt, system_prompt=system_prompt, max_tokens=max_tokens
            )

        now = time.monotonic()
        if now < self._breaker_open_until:
            raise LLMGenerationError(
                f"LLM circuit open for {self._breaker_open_until - now:.0f}s more "
                "(recent connection failure)"
            )

        model = await self.effective_chat_model()
        try:
            logger.info("LLM request model=%s base=%s", model, self._openai_base_url())

            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.config.temperature,
                    max_tokens=max_tokens,
                ),
                timeout=self.timeout,
            )
        except TimeoutError as e:
            logger.warning("LLM request timed out.")
            self._breaker_open_until = time.monotonic() + BREAKER_COOLDOWN_S
            raise LLMGenerationError("LLM request timed out") from e
        except Exception as e:
            logger.error("LLM Error: %s", e)
            self._breaker_open_until = time.monotonic() + BREAKER_COOLDOWN_S
            raise LLMGenerationError(f"LLM request failed: {e}") from e

        self._breaker_open_until = 0.0
        result = response.choices[0].message.content
        if not result or not result.strip():
            raise LLMGenerationError("LLM returned an empty response")
        return result.strip()
