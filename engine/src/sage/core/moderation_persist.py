"""Persist moderation settings to config/moderation.toml for restarts."""

from __future__ import annotations

from pathlib import Path

from sage.core.config import ModerationConfig
from sage.core.toml_persist import atomic_write_toml


def save_moderation_toml(cfg: ModerationConfig, path: Path | None = None) -> Path:
    target = path or Path("config/moderation.toml")
    lines = [
        "# Auto-written by SAGE Nexus (admin console, Players > Moderation). Safe to edit by hand.",
        "# Recording sign-in addresses is personal data in many countries: check your local rules",
        "# before turning it on. Players are told on the sign-in screen while it is on.",
        f"registration_open = {str(cfg.registration_open).lower()}",
        f"record_login_addresses = {str(cfg.record_login_addresses).lower()}",
        f"login_history_days = {int(cfg.login_history_days)}",
        f"report_cooldown_seconds = {int(cfg.report_cooldown_seconds)}",
        "",
    ]
    return atomic_write_toml(target, lines)
