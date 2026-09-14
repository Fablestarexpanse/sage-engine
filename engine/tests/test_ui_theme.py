"""World look for the player client: ui/theme.yaml."""

from __future__ import annotations

from pathlib import Path

from sage.world.ui_theme import load_ui_theme

ROOT = Path(__file__).resolve().parents[2]


def test_reference_worlds_ship_different_looks():
    from sage.world.package import available_worlds

    themes = [load_ui_theme(ROOT / "worlds" / w) for w in available_worlds(ROOT / "worlds")]
    assert len(themes) >= 2 and len({t["mark"] for t in themes}) == len(themes)
    rivermoot = load_ui_theme(ROOT / "worlds" / "rivermoot")
    assert rivermoot == {"mark": "≈", "accent": {"dark": "#d4a15a", "light": "#8a5a1c"}}


def test_missing_partial_and_invalid_files(tmp_path, caplog):
    assert load_ui_theme(tmp_path) == {}
    (tmp_path / "ui").mkdir()
    theme = tmp_path / "ui" / "theme.yaml"
    theme.write_text("accent:\n  dark: '#112233'\n", encoding="utf-8")
    assert load_ui_theme(tmp_path) == {"accent": {"dark": "#112233"}}
    theme.write_text("accent:\n  dark: teal\n", encoding="utf-8")
    assert load_ui_theme(tmp_path) == {}
    assert "Ignoring invalid" in caplog.text
