"""Dependency license report and policy for the SAGE engine (M2 phase 04).

Collects licenses for Python (requirements.lock, read from the installed environment), npm
(admin-ui, player-ui, worldforge package-lock.json) and Cargo (worldforge/src-tauri), classifies
each as permissive / weak / unknown / strong, and fails when a shipped dependency is strong
copyleft or unidentified and not in scripts/license_allowlist.toml.

    python scripts/license_report.py [--require-cargo] [--out license-report.md]

Run it in a clean environment with only requirements.lock installed; a shared interpreter
reports whatever versions it happens to have.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NPM_APPS = ("admin-ui", "player-ui", "worldforge")
CARGO_MANIFEST = ROOT / "worldforge" / "src-tauri" / "Cargo.toml"
ALLOWLIST = ROOT / "scripts" / "license_allowlist.toml"

RANK = {"permissive": 0, "weak": 1, "unknown": 2, "strong": 3}
PERMISSIVE_IDS = {
    "mit", "mit-0", "0bsd", "apache-2.0", "isc", "unlicense", "zlib", "psf-2.0",
    "python-2.0", "cc0-1.0", "cc-by-4.0", "blueoak-1.0.0", "x11", "bsd", "wtfpl",
}  # fmt: skip
PERMISSIVE_PREFIXES = ("bsd-", "unicode-")
WEAK_PREFIXES = ("lgpl", "mpl", "epl", "cddl")
STRONG_PREFIXES = ("gpl", "agpl", "sspl")
LONG_NAMES = {
    "mit license": "permissive",
    "apache software license": "permissive",
    "apache 2.0": "permissive",
    "apache license 2.0": "permissive",
    "apache license, version 2.0": "permissive",
    "bsd license": "permissive",
    "isc license (iscl)": "permissive",
    "python software foundation license": "permissive",
    "the unlicense (unlicense)": "permissive",
    "mozilla public license 2.0 (mpl 2.0)": "weak",
    "gnu lesser general public license v2 or later (lgplv2+)": "weak",
    "gnu lesser general public license v3 (lgplv3)": "weak",
    "gnu general public license v3 (gplv3)": "strong",
    "gnu general public license v2 (gplv2)": "strong",
}


@dataclass(frozen=True)
class Dependency:
    ecosystem: str
    name: str
    version: str
    license: str | None
    dev: bool
    source: str

    @property
    def category(self) -> str:
        return classify(self.license)


def _classify_id(token: str) -> str:
    base, _, exception = token.partition(" WITH ")
    if exception:
        # SPDX exceptions only loosen a license; GPL + Classpath/linking exceptions act like
        # weak copyleft for code that merely links the dependency.
        category = _classify_id(base)
        return "weak" if category == "strong" else category
    key = token.strip().lower().rstrip("+")
    key = re.sub(r"-(only|or-later)$", "", key)
    if not key:
        return "unknown"
    if key in LONG_NAMES:
        return LONG_NAMES[key]
    if key in PERMISSIVE_IDS or key.startswith(PERMISSIVE_PREFIXES):
        return "permissive"
    if key.startswith(STRONG_PREFIXES):
        return "strong"
    if key.startswith(WEAK_PREFIXES):
        return "weak"
    return "unknown"


def classify(expression: str | None) -> str:
    """Classify an SPDX-style expression. OR = most permissive branch, AND = most restrictive."""
    if not expression or not expression.strip():
        return "unknown"
    expr = expression.strip()
    if expr.lower() in LONG_NAMES:
        return LONG_NAMES[expr.lower()]
    while expr.startswith("(") and expr.endswith(")") and _balanced(expr[1:-1]):
        expr = expr[1:-1].strip()
    for operator, pick in ((" OR ", min), ("/", min), (" AND ", max)):
        parts = _split_top_level(expr, operator)
        if len(parts) > 1:
            return pick((classify(p) for p in parts), key=RANK.__getitem__)
    return _classify_id(expr)


def _balanced(text: str) -> bool:
    depth = 0
    for char in text:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0


def _split_top_level(expr: str, operator: str) -> list[str]:
    parts, depth, start, i = [], 0, 0, 0
    while i < len(expr):
        char = expr[i]
        if char in "()":
            depth += 1 if char == "(" else -1
        elif depth == 0 and expr.startswith(operator, i):
            parts.append(expr[start:i])
            i += len(operator)
            start = i
            continue
        i += 1
    parts.append(expr[start:])
    return [p.strip() for p in parts if p.strip()]


def python_license(meta) -> str | None:
    """License-Expression, else a short License field, else the trove classifier name."""
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    field = (meta.get("License") or "").strip()
    if field and len(field) <= 80 and "\n" not in field and field.upper() != "UNKNOWN":
        return field
    names = [
        c.split("::")[-1].strip()
        for c in (meta.get_all("Classifier") or [])
        if c.startswith("License ::")
    ]
    return " OR ".join(names) if names else None


def collect_python(lock: Path = ROOT / "engine" / "requirements.lock") -> list[Dependency]:
    deps = []
    for line in lock.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
        if not match:
            continue
        name, pinned = match.groups()
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            deps.append(Dependency("python", name, pinned, None, False, "not installed"))
            continue
        deps.append(
            Dependency("python", name, dist.version, python_license(dist.metadata), False, "lock")
        )
    return deps


def collect_npm(lock: Path) -> list[Dependency]:
    data = json.loads(lock.read_text(encoding="utf-8"))
    app = lock.parent.name
    deps = []
    for key, entry in data.get("packages", {}).items():
        if not key:
            continue
        name = key.rsplit("node_modules/", 1)[-1]
        deps.append(
            Dependency(
                "npm",
                name,
                entry.get("version", ""),
                entry.get("license"),
                bool(entry.get("dev")),
                app,
            )
        )
    return deps


def collect_cargo(manifest: Path = CARGO_MANIFEST) -> list[Dependency]:
    out = subprocess.run(
        [
            "cargo",
            "metadata",
            "--format-version",
            "1",
            "--locked",
            "--manifest-path",
            str(manifest),
        ],
        capture_output=True,
        check=True,
    ).stdout
    data = json.loads(out.decode("utf-8"))
    members = set(data.get("workspace_members", []))
    return [
        Dependency("cargo", p["name"], p["version"], p.get("license"), False, "worldforge")
        for p in data["packages"]
        if p["id"] not in members
    ]


def load_allowlist(path: Path = ALLOWLIST) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {(entry["ecosystem"], entry["name"]) for entry in data.get("allow", [])}


def policy_violations(deps: list[Dependency], allow: set[tuple[str, str]]) -> list[Dependency]:
    return [
        d
        for d in deps
        if not d.dev and d.category in ("strong", "unknown") and (d.ecosystem, d.name) not in allow
    ]


def render(deps: list[Dependency], allow: set[tuple[str, str]], notes: list[str]) -> str:
    lines = ["# SAGE dependency license report", ""]
    lines += [f"> {note}" for note in notes] + ([""] if notes else [])
    lines += ["| Ecosystem | Shipped | Dev-only | Permissive | Weak | Unknown | Strong |"]
    lines += ["|---|---|---|---|---|---|---|"]
    for eco in ("python", "npm", "cargo"):
        group = [d for d in deps if d.ecosystem == eco]
        if not group:
            continue
        shipped = [d for d in group if not d.dev]
        counts = {c: sum(1 for d in shipped if d.category == c) for c in RANK}
        lines.append(
            f"| {eco} | {len(shipped)} | {len(group) - len(shipped)} | {counts['permissive']} "
            f"| {counts['weak']} | {counts['unknown']} | {counts['strong']} |"
        )
    flagged = sorted(
        {(d.ecosystem, d.name, d.version, d.license, d.category, d.dev) for d in deps
         if d.category != "permissive"},
        key=lambda r: (-RANK[r[4]], r[0], r[1]),
    )  # fmt: skip
    lines += ["", "## Needs attention (non-permissive)", ""]
    lines += [
        "| Class | Ecosystem | Package | Version | License | Scope |",
        "|---|---|---|---|---|---|",
    ]
    for eco, name, version, license_, category, dev in flagged:
        scope = "dev-only" if dev else ("allowlisted" if (eco, name) in allow else "shipped")
        lines.append(f"| {category} | {eco} | {name} | {version} | {license_ or '—'} | {scope} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--require-cargo", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    notes: list[str] = []
    deps = collect_python()
    for app in NPM_APPS:
        deps += collect_npm(ROOT / app / "package-lock.json")
    if shutil.which("cargo"):
        deps += collect_cargo()
    elif args.require_cargo:
        print("cargo not found and --require-cargo given", file=sys.stderr)
        return 2
    else:
        notes.append("Cargo dependencies skipped: cargo not installed.")

    allow = load_allowlist()
    report = render(deps, allow, notes)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    violations = policy_violations(deps, allow)
    shipped = [d for d in deps if not d.dev]
    print(f"{len(deps)} dependencies ({len(shipped)} shipped); {len(violations)} policy violations")
    for d in violations:
        print(
            f"FAIL {d.ecosystem} {d.name} {d.version}: {d.license or 'no license'} ({d.category})"
        )
    for d in shipped:
        if d.category == "weak" and (d.ecosystem, d.name) not in allow:
            print(f"review {d.ecosystem} {d.name} {d.version}: {d.license} (weak copyleft)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
