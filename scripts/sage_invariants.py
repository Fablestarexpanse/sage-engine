"""SAGE invariant ratchet: world-specific terms and hardcoded player text in engine code.

Enforces brief invariants 2-4 (docs/sage/BRIEF.md section 3) as a ratchet: per-file counts may
only go down relative to scripts/sage_invariants_baseline.json. See
docs/sage/PHASE1_CONTRACTS.md Part E.

    python scripts/sage_invariants.py check    # CI: exit 1 if any file got worse
    python scripts/sage_invariants.py update   # rewrite the baseline after removing hits
    python scripts/sage_invariants.py report   # per-term totals
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DENYLIST_FILE = ROOT / "scripts" / "sage_denylist.toml"
BASELINE_FILE = ROOT / "scripts" / "sage_invariants_baseline.json"

# Engine code (NOTICE) plus repository tooling that ships beside it.
ENGINE_PATHS = ["engine", "scripts"]
EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".json",
    ".toml",
    ".rs",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {"node_modules", "dist", "target", "__pycache__", ".desloppify", ".pytest_cache"}
SKIP_FILES = {
    "package-lock.json",
    "Cargo.lock",
    "scripts/sage_invariants.py",
    "scripts/sage_denylist.toml",
    "scripts/sage_invariants_baseline.json",
    "engine/tests/test_sage_invariants.py",
}
CATEGORIES = ("denylist", "player_literals")


@dataclass
class Denylist:
    insensitive: list[str] = field(default_factory=list)
    sensitive: list[str] = field(default_factory=list)
    acronyms: list[str] = field(default_factory=list)

    def patterns(self) -> Iterator[tuple[str, re.Pattern[str], bool]]:
        """(canonical term, regex, literal_only) — longest terms first so "glyphstream"
        claims its span before "glyph". Sensitive terms are ordinary English words, so they
        only count inside string literals (a UI label), never in prose or identifiers."""
        rules = [(t, re.IGNORECASE, True, False) for t in self.insensitive]
        rules += [(t, 0, True, True) for t in self.sensitive]
        rules += [(t, 0, False, False) for t in self.acronyms]
        for term, flags, plural, literal_only in sorted(rules, key=lambda r: -len(r[0])):
            suffix = "(?:es|s)?" if plural else ""
            yield term.lower(), re.compile(re.escape(term) + suffix, flags), literal_only


def load_denylist(root: Path = ROOT) -> Denylist:
    data = tomllib.loads((root / "scripts" / "sage_denylist.toml").read_text(encoding="utf-8"))
    deny = Denylist(
        insensitive=list(data.get("insensitive", [])),
        sensitive=list(data.get("sensitive", [])),
        acronyms=list(data.get("acronyms", [])),
    )
    deny.insensitive += [t for t in world_terms(root) if t not in deny.insensitive]
    return deny


def world_terms(root: Path) -> list[str]:
    """Attribute and currency keys declared by world packages (invariant 4)."""
    terms: set[str] = set()
    for name in ("stats.yaml", "currencies.yaml"):
        for path in sorted((root / "worlds").glob(f"*/{name}")):
            for line in path.read_text(encoding="utf-8").splitlines():
                match = re.match(r"^\s*(?:-\s+)?key:\s*['\"]?([A-Za-z0-9_]+)", line)
                if match:
                    terms.add(match.group(1).lower())
    return sorted(terms)


def _is_boundary(text: str, start: int, end: int) -> bool:
    first, last = text[start], text[end - 1]
    if start > 0:
        prev = text[start - 1]
        # A letter or digit before the match joins the word, except a camelCase hump.
        if prev.isalnum() and not (prev.islower() and first.isupper()):
            return False
    if end < len(text):
        nxt = text[end]
        if nxt.isalnum() and not (last.islower() and nxt.isupper()):
            return False
    return True


def _in_string_literal(text: str, start: int) -> bool:
    """Heuristic: an odd number of quotes of one kind precedes the match on its line.
    Triple quotes are ignored, so docstring prose doesn't count as a literal."""
    line = text[text.rfind("\n", 0, start) + 1 : start]
    line = line.replace('"""', "").replace("'''", "")
    return any(line.count(q) % 2 == 1 for q in ('"', "'", "`"))


def find_terms(text: str, denylist: Denylist) -> Counter[str]:
    counts: Counter[str] = Counter()
    claimed: set[int] = set()
    for term, pattern, literal_only in denylist.patterns():
        for match in pattern.finditer(text):
            start, end = match.span()
            if start in claimed or not _is_boundary(text, start, end):
                continue
            if literal_only and (
                (start > 0 and text[start - 1].isalnum()) or not _in_string_literal(text, start)
            ):
                continue
            claimed.update(range(start, end))
            counts[term] += 1
    return counts


def _is_text_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Mod):
        return _is_text_expr(node.left) or _is_text_expr(node.right)
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and _is_text_expr(node.func.value)
    )


def count_player_literals(source: str) -> int:
    """Calls that hand a literal string to a player: send(text), broadcast(text), end(r, text)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    positions = {"send": 0, "broadcast": 0, "end": 1}
    total = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        index = positions.get(node.func.attr)
        if index is not None and len(node.args) > index and _is_text_expr(node.args[index]):
            total += 1
    return total


def _tracked_files(root: Path) -> set[str] | None:
    """Tracked plus new not-ignored files: ignored build output never skews counts vs CI."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {p for p in out.split("\0") if p}


def iter_engine_files(root: Path = ROOT) -> Iterator[tuple[str, Path]]:
    tracked = _tracked_files(root)
    for top in ENGINE_PATHS:
        base = root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in EXTENSIONS:
                continue
            rel = path.relative_to(root).as_posix()
            if SKIP_DIRS.intersection(path.relative_to(root).parts) or rel in SKIP_FILES:
                continue
            if path.name in SKIP_FILES or (tracked is not None and rel not in tracked):
                continue
            yield rel, path


def scan(root: Path = ROOT, denylist: Denylist | None = None) -> dict[str, dict[str, int]]:
    denylist = denylist or load_denylist(root)
    result: dict[str, dict[str, int]] = {name: {} for name in CATEGORIES}
    for rel, path in iter_engine_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        terms = sum(find_terms(text, denylist).values())
        if terms:
            result["denylist"][rel] = terms
        if path.suffix == ".py":
            literals = count_player_literals(text)
            if literals:
                result["player_literals"][rel] = literals
    return result


def term_totals(root: Path = ROOT) -> Counter[str]:
    denylist = load_denylist(root)
    totals: Counter[str] = Counter()
    for _, path in iter_engine_files(root):
        totals.update(find_terms(path.read_text(encoding="utf-8", errors="replace"), denylist))
    return totals


def compare(baseline: dict, current: dict) -> list[str]:
    violations = []
    for category in CATEGORIES:
        allowed = baseline.get(category, {})
        for rel, count in sorted(current.get(category, {}).items()):
            limit = allowed.get(rel, 0)
            if count > limit:
                violations.append(f"{category}: {rel} has {count}, baseline allows {limit}")
    return violations


def _totals(result: dict) -> dict[str, int]:
    return {category: sum(result[category].values()) for category in CATEGORIES}


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "check"
    if command == "report":
        for term, count in term_totals().most_common():
            print(f"{count:6d}  {term}")
        return 0

    current = scan()
    if command == "update":
        payload = {
            "totals": _totals(current),
            **{c: dict(sorted(current[c].items())) for c in CATEGORIES},
        }
        BASELINE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {payload['totals']}")
        return 0
    if command != "check":
        print(__doc__)
        return 2

    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    violations = compare(baseline, current)
    print(f"current {_totals(current)} / baseline {baseline.get('totals')}")
    for line in violations:
        print(f"FAIL {line}")
    improved = sum(
        1
        for c in CATEGORIES
        for rel, limit in baseline.get(c, {}).items()
        if current[c].get(rel, 0) < limit
    )
    if improved and not violations:
        print(f"{improved} file counts dropped; run `update` to lock in the lower baseline")
    if violations:
        print("Engine code gained world-specific terms or hardcoded player text. Move it to a")
        print("world package or lexicon key; never raise the baseline to make this pass.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
