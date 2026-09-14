"""TOML config loading — merges all config/*.toml files into a single Config object."""

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

logger = logging.getLogger(__name__)

ENV_PREFIX = "SAGE_"
# Pre-rename prefix, accepted for one release (docs/sage/PHASE1_CONTRACTS.md F.1).
LEGACY_ENV_PREFIX = "FABLESTAR_"


def env_setting(name: str) -> str:
    """A named SAGE_<name> environment variable, falling back to the legacy prefix."""
    value = os.environ.get(ENV_PREFIX + name, "").strip()
    return value or os.environ.get(LEGACY_ENV_PREFIX + name, "").strip()


class ServerConfig(BaseModel):
    """Players connect via WebSocket on `websocket_port` (Nexus /play). Telnet is not used."""

    websocket_port: int = 4001
    # World package to run from worlds_dir (a directory name). Optional when only one exists.
    world: str | None = None
    worlds_dir: str = "worlds"
    max_connections: int = 100
    tick_rate: float = 0.25  # 4 ticks per second
    dev_mode: bool = False
    # Passwordless test logins via POST /play/dev/login, loopback clients only.
    # Needs dev_mode too; never enable on a networked host.
    dev_login: bool = False
    # When True, Nexus admin/content/forge/llm routes require a staff JWT (see /admin/auth/login).
    admin_auth_required: bool = True
    # HS256 secret; prefer env SAGE_ADMIN_JWT_SECRET in production.
    admin_jwt_secret: str | None = None
    # Allowed CORS origins for the admin and player UIs. Defaults to localhost dev ports.
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ]
    )


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str = "fablestar"
    user: str = "fablestar"
    password: str | None = None
    pool_size: int = 10


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None


# comfyui.toml keys renamed in SAGE 0.2 (3.14c); the old names are read for one release.
_COMFYUI_RENAMED_KEYS = {
    "starting_echo_credits": "starting_ai_credits",
    "pixels_per_usd": "credits_per_usd",
}


class CreditBundle(BaseModel):
    """One [[credit_bundles]] entry in comfyui.toml: a priced pack of AI art credits."""

    id: str
    label: str
    credits: int = Field(gt=0)
    blurb: str = ""


class ComfyUIConfig(BaseModel):
    """Optional ComfyUI HTTP API for character portraits and room area art."""

    @model_validator(mode="before")
    @classmethod
    def _renamed_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        old = [k for k in _COMFYUI_RENAMED_KEYS if k in data]
        if old:
            logger.warning(
                "Deprecated comfyui.toml keys %s: rename to %s",
                old,
                [_COMFYUI_RENAMED_KEYS[k] for k in old],
            )
            data = dict(data)
            for key in old:
                data.setdefault(_COMFYUI_RENAMED_KEYS[key], data.pop(key))
        return data

    enabled: bool = False
    base_url: str = "http://127.0.0.1:8188"
    # Defaults match shipped graphs: character portrait (CLIP 57 + SaveImage 40) vs area (34 + 31).
    # If comfyui.toml omits keys, we must NOT fall back to legacy SDXL example workflows.
    # Empty: the world's ai/comfyui/portrait.json. A path here (relative to the project root)
    # overrides it for this deployment.
    workflow_path: str = ""
    positive_prompt_node_id: str = "57"
    output_node_id: str = "40"
    # Empty: the world's ai/comfyui/area.json, else the portrait graph.
    area_workflow_path: str = ""
    area_positive_prompt_node_id: str = "16"
    area_output_node_id: str = "17"
    # If set, replaces inputs.ckpt_name on every CheckpointLoaderSimple node (avoids editing JSON).
    checkpoint_name: str = ""
    timeout_seconds: float = 600.0
    poll_interval_seconds: float = 0.75
    # Player image generation economy (account ai_credits); label is the art currency's display name.
    economy_enabled: bool = True
    starting_ai_credits: int = 50
    portrait_generation_cost: int = 3
    area_generation_cost: int = 3
    character_create_portrait_cost: int = 3
    currency_display_name: str = "credits"
    # Reference rate for storefront / admin bundle math (not enforced server-side).
    credits_per_usd: int = 100
    # Purchase bundles staff can grant from the admin console (deployment pricing; none by default).
    credit_bundles: list[CreditBundle] = Field(default_factory=list)


class LLMConfig(BaseModel):
    primary_backend: str = "lm_studio"
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_key: str = "not-needed"
    ollama_url: str = "http://localhost:11434/v1"
    anthropic_key: SecretStr | None = None
    timeout_seconds: float = 10.0
    cache_ttl: int = 3600
    # OpenAI-compatible chat id, or "auto" / "*" / "" to use the loaded model (first listed).
    chat_model: str = "auto"
    temperature: float = 0.7

    @field_validator("lm_studio_url", "ollama_url")
    @classmethod
    def _normalize_openai_base(cls, v: str) -> str:
        from sage.core.openai_util import normalize_openai_compatible_base

        return normalize_openai_compatible_base(v)


class AgentsLLMConfig(LLMConfig):
    """Agent-brain LLM: an external endpoint OR an in-process GGUF model.

    primary_backend accepts "lm_studio" / "ollama" (OpenAI-compatible HTTP)
    or "embedded" (llama-cpp-python loads model_path inside the server).
    """

    enabled: bool = False
    # GGUF file for the embedded backend, e.g. "models/qwen2.5-3b-instruct-q4_k_m.gguf".
    model_path: str = ""
    # Embedded context window; small models + short prompts keep this modest.
    embedded_ctx: int = 4096


class Config(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    # Loaded from config/agents_llm.toml (section name = file stem).
    agents_llm: AgentsLLMConfig = Field(default_factory=AgentsLLMConfig)
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)


def load_config(config_dir: str = "config") -> Config:
    """Load configuration from TOML files in the specified directory."""
    config_path = Path(config_dir)
    data: dict[str, Any] = {}

    # Load all .toml files in the config directory
    if config_path.exists():
        for toml_file in config_path.glob("*.toml"):
            section_name = toml_file.stem
            with open(toml_file, "rb") as f:
                section_data = tomllib.load(f)
                data[section_name] = section_data

    # Environment overrides: SAGE_<SECTION>__<FIELD>=value (e.g. SAGE_SERVER__WEBSOCKET_PORT=8001).
    # Legacy FABLESTAR_ keys apply first so a SAGE_ key for the same setting wins.
    legacy_keys = []
    for prefix in (LEGACY_ENV_PREFIX, ENV_PREFIX):
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            parts = key[len(prefix) :].lower().split("__")
            if len(parts) != 2:
                continue
            section, field = parts
            data.setdefault(section, {})[field] = value
            if prefix == LEGACY_ENV_PREFIX:
                legacy_keys.append(key)
    if legacy_keys:
        logger.warning(
            "Deprecated environment variables %s: rename the FABLESTAR_ prefix to SAGE_ "
            "(support ends next release).",
            ", ".join(sorted(legacy_keys)),
        )

    return Config(**data)


def resolve_project_root() -> Path:
    """
    Base directory for repo-relative paths (config/*.json, content/, data/).

    Order: SAGE_PROJECT_ROOT env, cwd if it contains config/, else walk upward
    from this package until a config/ directory is found, else cwd.
    """
    env = env_setting("PROJECT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "config").is_dir():
        return cwd
    start = Path(__file__).resolve().parent
    for anc in [start, *start.parents]:
        if (anc / "config").is_dir():
            return anc
    return cwd


# The running world's ai/comfyui directory (set by the server at startup).
_world_comfyui_dir: Path | None = None


def set_world_comfyui_dir(path: Path | None) -> None:
    global _world_comfyui_dir
    _world_comfyui_dir = Path(path) if path is not None else None


def resolve_workflow_path(cfg: ComfyUIConfig, role: str) -> Path:
    """The ComfyUI graph for a role ("portrait" | "area").

    A path in comfyui.toml wins when the file exists. Otherwise the world's
    ``ai/comfyui/<role>.json`` is used (a configured path that no longer exists falls back to it
    with a warning, so a deployment whose toml still names a moved file keeps working). An
    area role with nothing of its own uses the portrait graph.
    """
    role = "area" if (role or "").lower().strip() == "area" else "portrait"
    configured = (cfg.area_workflow_path if role == "area" else cfg.workflow_path or "").strip()
    world_file = _world_comfyui_dir / f"{role}.json" if _world_comfyui_dir else None
    if configured:
        path = resolve_config_asset_path(configured)
        if path.is_file() or world_file is None or not world_file.is_file():
            return path
        logger.warning(
            "ComfyUI %s workflow %s not found; using the world's %s", role, path, world_file
        )
        return world_file
    if world_file is not None and world_file.is_file():
        return world_file
    if role == "area":
        return resolve_workflow_path(cfg, "portrait")
    return world_file if world_file is not None else Path("")


def resolve_config_asset_path(relative_or_absolute: str) -> Path:
    """Resolve a path from comfyui.toml (or defaults) against the project root when relative."""
    s = (relative_or_absolute or "").strip()
    if not s:
        return Path(s)
    p = Path(s)
    if p.is_absolute():
        return p.resolve()
    return (resolve_project_root() / p).resolve()
