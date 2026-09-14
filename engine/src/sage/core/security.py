"""Shared token-signing secret resolution.

The one JWT secret signs both staff tokens (admin_security) and player play
tokens (services/play_tokens) — the "kind" claim keeps the audiences apart.
It lives in core/ so neither side has to import the other's package for it.
"""

from __future__ import annotations

from typing import Any

from sage.core.config import env_setting


def jwt_secret_for_server(server: Any) -> str:
    cfg = server.config.server
    env = env_setting("ADMIN_JWT_SECRET")
    if env:
        return env
    if cfg.admin_jwt_secret and str(cfg.admin_jwt_secret).strip():
        return str(cfg.admin_jwt_secret).strip()
    if cfg.admin_auth_required:
        raise RuntimeError(
            "admin_auth_required is true but no JWT secret is configured. "
            "Set SAGE_ADMIN_JWT_SECRET env var or admin_jwt_secret in server.toml. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    # dev_mode only — auth is disabled, secret value is never used to validate real tokens
    return "dev-only-no-auth"
