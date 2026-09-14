"""Release gate for development-only code (passwordless dev logins).

Dev-only code is marked so it can be found and removed mechanically:

- a whole file carries `DEV-AUTH:FILE` in its first five lines;
- a block of lines sits between a `DEV-AUTH:BEGIN` line and a `DEV-AUTH:END` line (both removed
  with it), in any language's comment syntax.

    python scripts/release_check.py           # list what is left; exit 1 if anything is
    python scripts/release_check.py --strip   # delete marked files and blocks, then re-check

After stripping, live code, config and top-level docs are scanned for dev-login residue (a route,
config key or client call left outside the markers). Residue fails the check too: fix it by hand
and mark it next time. Run on a release branch or worktree, then run the tests and client builds.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "DEV-AUTH"
FILE_MARK = f"{TAG}:FILE"
BEGIN = f"{TAG}:BEGIN"
END = f"{TAG}:END"
# Files that talk about the markers without being dev code.
SELF = {"scripts/release_check.py", "engine/tests/test_release_check.py"}
# Where leftover dev-login references would ship. Historical notes (CHANGELOG, docs/dev) stay.
RESIDUE_PATHS = (
    "engine/src/",
    "engine/clients/admin-ui/src/",
    "engine/clients/player-ui/src/",
    "config/",
    "README.md",
    "CLAUDE.md",
)
RESIDUE = re.compile(r"dev_login|/dev/login|/dev/status|playDevLogin|adminDevLogin|dev-staff")
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".toml", ".md", ".yaml", ".yml", ".json", ".css", ".html",
}  # fmt: skip


@dataclass
class Report:
    files: list[str] = field(default_factory=list)
    blocks: list[tuple[str, int, int]] = field(default_factory=list)  # path, begin, end (1-based)
    errors: list[str] = field(default_factory=list)
    residue: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.files or self.blocks or self.errors or self.residue)


def find_blocks(path: str, lines: list[str]) -> tuple[list[tuple[int, int]], list[str]]:
    """(begin, end) line indexes (0-based, inclusive) of marked blocks, plus marker errors."""
    blocks: list[tuple[int, int]] = []
    errors: list[str] = []
    start: int | None = None
    for i, line in enumerate(lines):
        if BEGIN in line:
            if start is not None:
                errors.append(f"{path}:{i + 1}: {BEGIN} inside an open block (line {start + 1})")
            start = i
        elif END in line:
            if start is None:
                errors.append(f"{path}:{i + 1}: {END} without {BEGIN}")
            else:
                blocks.append((start, i))
                start = None
    if start is not None:
        errors.append(f"{path}:{start + 1}: {BEGIN} never closed")
    return blocks, errors


def strip_blocks(lines: list[str], blocks: list[tuple[int, int]]) -> list[str]:
    drop = {i for a, b in blocks for i in range(a, b + 1)}
    return [line for i, line in enumerate(lines) if i not in drop]


def is_marked_file(lines: list[str]) -> bool:
    return any(FILE_MARK in line for line in lines[:5])


def candidate_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        p
        for p in out.splitlines()
        if Path(p).suffix in TEXT_SUFFIXES and p not in SELF and (root / p).is_file()
    )


def _read(root: Path, rel: str) -> list[str] | None:
    try:
        return (root / rel).read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def scan(root: Path, paths: list[str]) -> Report:
    report = Report()
    for rel in paths:
        lines = _read(root, rel)
        if lines is None:
            continue
        if is_marked_file(lines):
            report.files.append(rel)
            continue
        blocks, errors = find_blocks(rel, lines)
        report.errors.extend(errors)
        report.blocks.extend((rel, a + 1, b + 1) for a, b in blocks)
        if rel.startswith(RESIDUE_PATHS):
            drop = {i for a, b in blocks for i in range(a, b + 1)}
            for i, line in enumerate(lines):
                if i not in drop and RESIDUE.search(line):
                    report.residue.append((rel, i + 1, line.strip()))
    return report


def strip(root: Path, paths: list[str]) -> Report:
    """Delete marked files and blocks. Returns what was removed; refuses on marker errors."""
    report = scan(root, paths)
    if report.errors:
        return report
    for rel in report.files:
        (root / rel).unlink()
    touched = sorted({rel for rel, _, _ in report.blocks})
    for rel in touched:
        lines = _read(root, rel) or []
        blocks, _ = find_blocks(rel, lines)
        (root / rel).write_text("".join(strip_blocks(lines, blocks)), encoding="utf-8", newline="")
    return report


def _print(report: Report, verb: str) -> None:
    for rel in report.files:
        print(f"{verb} file   {rel}")
    for rel, a, b in report.blocks:
        print(f"{verb} block  {rel}:{a}-{b}")
    for err in report.errors:
        print(f"ERROR  {err}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--strip", action="store_true", help="delete marked files and blocks")
    args = ap.parse_args(argv)

    if args.strip:
        removed = strip(ROOT, candidate_files(ROOT))
        _print(removed, "removed")
        if removed.errors:
            print("Nothing stripped: fix the marker errors first.")
            return 1
    report = scan(ROOT, candidate_files(ROOT))
    if not args.strip:
        _print(report, "dev-only")
    for rel, line, text in report.residue:
        print(f"RESIDUE  {rel}:{line}: {text}")
    if report.clean:
        print("release_check: no development-only auth code left.")
        return 0
    if args.strip and not (report.files or report.blocks or report.errors):
        print("release_check: stripped, but dev-login references remain outside the markers.")
    else:
        print("release_check: development-only code present. Run with --strip on a release branch.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
