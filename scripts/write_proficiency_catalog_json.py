"""Write content/proficiencies/catalog.json from builtin leaf rows (run after editing data/*.py)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sage.proficiencies.catalog_loader import leaf_definitions_from_builtin_rows  # noqa: E402
from sage.proficiencies.data import EXPECTED_LEAF_COUNT  # noqa: E402
from sage.proficiencies.models import ProficiencyCatalogDocument  # noqa: E402


def main() -> None:
    leaves = leaf_definitions_from_builtin_rows()
    doc = ProficiencyCatalogDocument(
        version=1,
        expected_leaf_count=EXPECTED_LEAF_COUNT,
        leaves=leaves,
    )
    out = ROOT / "content" / "proficiencies" / "catalog.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(leaves)} leaves)")


if __name__ == "__main__":
    main()
