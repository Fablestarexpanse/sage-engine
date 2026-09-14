"""scripts/release_check.py finds and strips development-only code (dev logins) for release."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "release_check", ROOT / "scripts" / "release_check.py"
)
rc = importlib.util.module_from_spec(_spec)
sys.modules["release_check"] = rc  # dataclasses resolve their module by name
_spec.loader.exec_module(rc)

B, E, F = rc.BEGIN, rc.END, rc.FILE_MARK


def _tree(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return sorted(files)


def test_strip_removes_marked_files_and_blocks_and_keeps_the_rest(tmp_path):
    paths = _tree(
        tmp_path,
        {
            "engine/src/app.py": f"a = 1\n# {B}\ndev = True\n# {E}\nb = 2\n",
            "engine/src/dev.py": f"# {F}\nsecret = 1\n",
            "engine/clients/player-ui/src/App.jsx": f"<A />\n{{/* {B} */}}\n<Dev />\n{{/* {E} */}}\n",
            "README.md": "plain\n",
        },
    )
    report = rc.strip(tmp_path, paths)
    assert report.files == ["engine/src/dev.py"]
    assert len(report.blocks) == 2
    assert not (tmp_path / "engine/src/dev.py").exists()
    assert (tmp_path / "engine/src/app.py").read_text(encoding="utf-8") == "a = 1\nb = 2\n"
    assert (tmp_path / "engine/clients/player-ui/src/App.jsx").read_text(
        encoding="utf-8"
    ) == "<A />\n"
    assert rc.scan(tmp_path, ["engine/src/app.py", "README.md"]).clean


@pytest.mark.parametrize(
    "text",
    [f"# {B}\nx\n", f"x\n# {E}\n", f"# {B}\n# {B}\n# {E}\n"],
    ids=["unclosed", "end-without-begin", "nested"],
)
def test_bad_markers_refuse_to_strip_anything(tmp_path, text):
    paths = _tree(tmp_path, {"engine/src/app.py": text, "engine/src/dev.py": f"# {F}\n"})
    report = rc.strip(tmp_path, paths)
    assert report.errors
    assert (tmp_path / "engine/src/dev.py").exists()
    assert (tmp_path / "engine/src/app.py").read_text(encoding="utf-8") == text


def test_unmarked_dev_login_reference_in_live_code_is_residue(tmp_path):
    paths = _tree(
        tmp_path,
        {
            "engine/src/cfg.py": "dev_login = False\n",
            "config/server.example.toml": f"# {B}\ndev_login = false\n# {E}\n",
            "docs/dev/old_notes.md": "we used dev_login for QA\n",
        },
    )
    report = rc.scan(tmp_path, paths)
    assert [(r[0], r[1]) for r in report.residue] == [("engine/src/cfg.py", 1)]


def test_repository_markers_are_well_formed():
    report = rc.scan(ROOT, rc.candidate_files(ROOT))
    assert report.errors == []
