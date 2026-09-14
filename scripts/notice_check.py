"""NOTICE must account for the repository as it is.

NOTICE is the document that says which terms cover which path, so a path it does not name is a
path with no stated license, and a path it names that no longer exists is a stale grant. This
check fails on either:

- a tracked top-level file or directory that NOTICE does not list;
- a world package (`worlds/<id>/`) that NOTICE does not list, or a world without a LICENSE file
  whose NOTICE line does not say it is proprietary;
- a LICENSE file below a listed directory whose own directory NOTICE does not list (a plugin or
  subtree with different terms must be named, not implied);
- a path listed in NOTICE that git does not track.

Listed paths are the lines in NOTICE indented by exactly two spaces; the first word is the path
(directories end with "/").

    python scripts/notice_check.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = re.compile(r"^  (\S+)(.*)$")
LICENSE_FILE = re.compile(r"(^|/)(LICENSE|LICENCE|COPYING)(\.[A-Za-z]+)?$")


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def notice_entries(text: str) -> dict[str, str]:
    """{path without trailing slash: the rest of its first line} for every listed path."""
    entries: dict[str, str] = {}
    for line in text.splitlines():
        match = ENTRY.match(line)
        if match:
            entries[match.group(1).rstrip("/")] = match.group(2)
    return entries


def problems(files: list[str], notice: str) -> list[str]:
    entries = notice_entries(notice)
    found: list[str] = []
    dirs = {"/".join(f.split("/")[:i]) for f in files for i in range(1, f.count("/") + 1)}
    existing = set(files) | dirs

    for top in sorted({f.split("/")[0] for f in files}):
        if top not in entries:
            found.append(f"{top}: top-level path not listed in NOTICE")

    worlds = sorted({"/".join(f.split("/")[:2]) for f in files if f.startswith("worlds/")} & dirs)
    for world in worlds:
        if world not in entries:
            found.append(f"{world}/: world package not listed in NOTICE")
        elif f"{world}/LICENSE" not in files and "proprietary" not in entries[world].lower():
            found.append(f"{world}/: no LICENSE file, and NOTICE does not call it proprietary")

    for f in files:
        if LICENSE_FILE.search(f) and "/" in f:
            directory = f.rsplit("/", 1)[0]
            if directory not in entries:
                found.append(f"{f}: license file in a directory NOTICE does not list")

    for path in sorted(entries):
        if path not in existing:
            found.append(f"{path}: listed in NOTICE but not in the repository")
    return found


def main() -> int:
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    found = problems(tracked_files(ROOT), notice)
    for line in found:
        print(f"NOTICE  {line}")
    if found:
        print("notice_check: NOTICE does not match the repository; add or fix the entries above.")
        return 1
    print("notice_check: every top-level path and world package is accounted for in NOTICE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
