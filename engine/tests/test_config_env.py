"""SAGE_ environment overrides, with FABLESTAR_ accepted for one release (contracts F.1)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sage.core import config as config_mod
from sage.core.config import env_setting, load_config


@pytest.fixture
def empty_config_dir(tmp_path: Path) -> str:
    return str(tmp_path)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for prefix in ("SAGE_", "FABLESTAR_"):
        for name in ("SERVER__WEBSOCKET_PORT", "ADMIN_JWT_SECRET", "PROJECT_ROOT"):
            monkeypatch.delenv(prefix + name, raising=False)


def test_sage_prefix_overrides_config(monkeypatch, empty_config_dir):
    _clear(monkeypatch)
    monkeypatch.setenv("SAGE_SERVER__WEBSOCKET_PORT", "9101")
    assert load_config(empty_config_dir).server.websocket_port == 9101


def test_legacy_prefix_still_works_and_warns(monkeypatch, empty_config_dir, caplog):
    _clear(monkeypatch)
    monkeypatch.setenv("FABLESTAR_SERVER__WEBSOCKET_PORT", "9102")
    with caplog.at_level(logging.WARNING, logger=config_mod.__name__):
        assert load_config(empty_config_dir).server.websocket_port == 9102
    assert "FABLESTAR_SERVER__WEBSOCKET_PORT" in caplog.text
    assert "SAGE_" in caplog.text


def test_sage_prefix_wins_over_legacy(monkeypatch, empty_config_dir):
    _clear(monkeypatch)
    monkeypatch.setenv("FABLESTAR_SERVER__WEBSOCKET_PORT", "9103")
    monkeypatch.setenv("SAGE_SERVER__WEBSOCKET_PORT", "9104")
    assert load_config(empty_config_dir).server.websocket_port == 9104


def test_env_setting_reads_named_variables(monkeypatch):
    _clear(monkeypatch)
    assert env_setting("ADMIN_JWT_SECRET") == ""
    monkeypatch.setenv("FABLESTAR_ADMIN_JWT_SECRET", "legacy")
    assert env_setting("ADMIN_JWT_SECRET") == "legacy"
    monkeypatch.setenv("SAGE_ADMIN_JWT_SECRET", "current")
    assert env_setting("ADMIN_JWT_SECRET") == "current"


def test_live_tests_flag_is_not_a_config_override(monkeypatch, empty_config_dir):
    _clear(monkeypatch)
    monkeypatch.setenv("SAGE_LIVE_TESTS", "1")
    load_config(empty_config_dir)  # no "live_tests" section, no crash


def test_renamed_comfyui_keys_still_load_with_a_warning(caplog):
    from sage.core.config import _COMFYUI_RENAMED_KEYS, ComfyUIConfig

    legacy = dict(zip(_COMFYUI_RENAMED_KEYS, (7, 250), strict=True))
    with caplog.at_level("WARNING"):
        cfg = ComfyUIConfig(**legacy)
    assert (cfg.starting_ai_credits, cfg.credits_per_usd) == (7, 250)
    assert set(_COMFYUI_RENAMED_KEYS.values()) == {"starting_ai_credits", "credits_per_usd"}
    assert "Deprecated comfyui.toml keys" in caplog.text
    old_start = next(k for k, v in _COMFYUI_RENAMED_KEYS.items() if v == "starting_ai_credits")
    # The new name wins when both are present.
    assert ComfyUIConfig(starting_ai_credits=9, **{old_start: 7}).starting_ai_credits == 9
