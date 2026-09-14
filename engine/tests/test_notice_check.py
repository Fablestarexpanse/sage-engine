"""scripts/notice_check.py: NOTICE names every top-level path and world, and nothing that is gone."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("notice_check", ROOT / "scripts" / "notice_check.py")
nc = importlib.util.module_from_spec(_spec)
sys.modules["notice_check"] = nc
_spec.loader.exec_module(nc)

FILES = [
    "README.md",
    "engine/LICENSE",
    "engine/src/sage/app.py",
    "plugins/LICENSE",
    "plugins/shop/plugin.toml",
    "worlds/open/LICENSE",
    "worlds/open/world.toml",
    "worlds/closed/world.toml",
]
NOTICE = """NOTICE

Engine:
  engine/               engine
  README.md
  plugins/              plugins
World packages:
  worlds/
  worlds/open/         open world
  worlds/closed/        proprietary, all rights reserved
"""


def test_a_matching_notice_passes():
    assert nc.problems(FILES, NOTICE) == []


def test_new_top_level_directory_fails():
    found = nc.problems([*FILES, "tools/thing.py"], NOTICE)
    assert found == ["tools: top-level path not listed in NOTICE"]


def test_new_world_package_fails():
    found = nc.problems([*FILES, "worlds/third/world.toml"], NOTICE)
    assert found == ["worlds/third/: world package not listed in NOTICE"]


def test_unlicensed_world_must_be_called_proprietary():
    notice = NOTICE.replace("proprietary, all rights reserved", "a world")
    assert nc.problems(FILES, notice) == [
        "worlds/closed/: no LICENSE file, and NOTICE does not call it proprietary"
    ]


def test_plugin_with_its_own_license_must_be_listed():
    found = nc.problems([*FILES, "plugins/shop/LICENSE"], NOTICE)
    assert found == ["plugins/shop/LICENSE: license file in a directory NOTICE does not list"]
    notice = NOTICE + "  plugins/shop/          Apache-2.0\n"
    assert nc.problems([*FILES, "plugins/shop/LICENSE"], notice) == []


def test_listed_path_that_is_gone_fails():
    notice = NOTICE + "  engine/src/sage/agents/   old path\n"
    assert nc.problems(FILES, notice) == [
        "engine/src/sage/agents: listed in NOTICE but not in the repository"
    ]


def test_repository_notice_matches_the_tree():
    assert nc.problems(nc.tracked_files(ROOT), (ROOT / "NOTICE").read_text(encoding="utf-8")) == []
