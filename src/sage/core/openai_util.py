"""Shared helpers for OpenAI-compatible HTTP bases (LM Studio, Ollama)."""


def normalize_openai_compatible_base(url: str) -> str:
    """
    AsyncOpenAI calls GET/POST relative to base_url, e.g. GET {base}/models.
    base_url must end with /v1 so the real path is /v1/models. If base is only
    http://host:1234, LM Studio logs "GET /models" and returns 200 with a warning.
    """
    u = (url or "").strip().rstrip("/")
    if not u:
        return "http://localhost:1234/v1"
    if u.endswith("/v1"):
        return u
    return f"{u}/v1"
