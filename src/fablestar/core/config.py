"""TOML config loading — merges all config/*.toml files into a single Config object."""

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator


class ServerConfig(BaseModel):
    """Players connect via WebSocket on `websocket_port` (Nexus /play). Telnet is not used."""

    websocket_port: int = 4001
    max_connections: int = 100
    tick_rate: float = 0.25  # 4 ticks per second
    dev_mode: bool = False
    # Passwordless test logins via POST /play/dev/login, loopback clients only.
    # Needs dev_mode too; never enable on a networked host.
    dev_login: bool = False
    # Shown in client UI for in-world economy (wallet / vendors); not the ComfyUI art balance.
    game_currency_display_name: str = "Digi"
    # Starting in-world balance for each new character (existing rows default 0 until granted in-game).
    starting_digi_balance: int = 100
    # When True, personal combat uses max(legacy strength/dexterity-derived, proficiency-derived) ratings.
    proficiency_combat_hybrid: bool = True
    # When True, Nexus admin/content/forge/llm routes require a staff JWT (see /admin/auth/login).
    admin_auth_required: bool = True
    # HS256 secret; prefer env FABLESTAR_ADMIN_JWT_SECRET in production.
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


class ComfyUIConfig(BaseModel):
    """Optional ComfyUI HTTP API for character portraits and room area art."""

    enabled: bool = False
    base_url: str = "http://127.0.0.1:8188"
    # Defaults match shipped graphs: character portrait (CLIP 57 + SaveImage 40) vs area (34 + 31).
    # If comfyui.toml omits keys, we must NOT fall back to legacy SDXL example workflows.
    workflow_path: str = "config/comfyui_character_portrait_workflow.json"
    positive_prompt_node_id: str = "57"
    output_node_id: str = "40"
    area_workflow_path: str = "config/comfyui_scene_workflow.json"
    area_positive_prompt_node_id: str = "16"
    area_output_node_id: str = "17"
    # If set, replaces inputs.ckpt_name on every CheckpointLoaderSimple node (avoids editing JSON).
    checkpoint_name: str = ""
    timeout_seconds: float = 600.0
    poll_interval_seconds: float = 0.75
    # Player image generation economy (account echo_credits); label is the art currency (e.g. pixels).
    economy_enabled: bool = True
    starting_echo_credits: int = 50
    portrait_generation_cost: int = 3
    area_generation_cost: int = 3
    character_create_portrait_cost: int = 3
    currency_display_name: str = "pixels"
    # Reference rate for storefront / admin bundle math (not enforced server-side).
    pixels_per_usd: int = 100


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
        from fablestar.core.openai_util import normalize_openai_compatible_base

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

    # Environment variables can override (e.g., FABLESTAR_SERVER__WEBSOCKET_PORT=8001)
    # This is a simplified version of env override
    for key, value in os.environ.items():
        if key.startswith("FABLESTAR_"):
            parts = key[10:].lower().split("__")
            if len(parts) == 2:
                section, field = parts
                if section not in data:
                    data[section] = {}
                data[section][field] = value

    return Config(**data)


def resolve_project_root() -> Path:
    """
    Base directory for repo-relative paths (config/*.json, content/, data/).

    Order: FABLESTAR_PROJECT_ROOT env, cwd if it contains config/, else walk upward
    from this package until a config/ directory is found, else cwd.
    """
    env = (os.environ.get("FABLESTAR_PROJECT_ROOT") or "").strip()
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


def resolve_config_asset_path(relative_or_absolute: str) -> Path:
    """Resolve a path from comfyui.toml (or defaults) against the project root when relative."""
    s = (relative_or_absolute or "").strip()
    if not s:
        return Path(s)
    p = Path(s)
    if p.is_absolute():
        return p.resolve()
    return (resolve_project_root() / p).resolve()
