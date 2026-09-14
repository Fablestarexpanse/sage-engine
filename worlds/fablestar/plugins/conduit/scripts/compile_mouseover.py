"""Compile content/proficiencies/mouseover/*.pipe.txt into leaf_descriptions.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PLUGIN = Path(__file__).resolve().parents[1]
MOUSE_DIR = PLUGIN.parents[1] / "content" / "proficiencies" / "mouseover"
OUT_PATH = PLUGIN.parents[1] / "content" / "proficiencies" / "leaf_descriptions.json"
CATALOG_PATH = PLUGIN.parents[1] / "content" / "proficiencies" / "catalog.json"


def _parse_line(line: str) -> tuple[str, str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 3:
        return None
    return parts[0], parts[1], parts[2]


def main() -> int:
    rows: dict[str, dict[str, str]] = {}
    for path in sorted(MOUSE_DIR.glob("*.pipe.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_line(line)
            if not parsed:
                continue
            lid, name, desc = parsed
            if lid in rows:
                print(f"duplicate id: {lid}", file=sys.stderr)
                return 1
            rows[lid] = {"name": name, "description": desc}

    if CATALOG_PATH.is_file():
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cat_ids = {leaf["id"] for leaf in catalog.get("leaves", [])}
        unknown = sorted(set(rows) - cat_ids)
        missing = sorted(cat_ids - set(rows))
        if unknown:
            print("ids in mouseover not in catalog.json:", unknown[:20], file=sys.stderr)
            return 1
        if missing:
            print("catalog leaves missing from mouseover:", len(missing), file=sys.stderr)
            return 1

    OUT_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} entries to {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
