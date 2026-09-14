"""Load proficiency catalog from content/proficiencies/*.json + optional overrides."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from .data import EXPECTED_LEAF_COUNT, all_builtin_leaf_rows
from .models import ProficiencyCatalogDocument, ProficiencyLeafDefinition
from .validation import validate_leaf_definitions

logger = logging.getLogger(__name__)


def _merge_leaf_descriptions_overlay(
    leaves: list[ProficiencyLeafDefinition], prof_dir: Path
) -> list[ProficiencyLeafDefinition]:
    """Merge display name + prose from leaf_descriptions.json (built from mouseover/*.pipe.txt)."""
    path = prof_dir / "leaf_descriptions.json"
    if not path.is_file():
        return leaves
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read %s: %s", path, e)
        return leaves
    if not isinstance(data, dict):
        return leaves
    by_id = {x.id: x for x in leaves}
    for lid, meta in data.items():
        leaf = by_id.get(str(lid))
        if leaf is None or not isinstance(meta, dict):
            continue
        name = meta.get("name")
        desc = meta.get("description")
        updates: dict[str, Any] = {}
        if isinstance(desc, str) and desc.strip():
            updates["description"] = desc.strip()
        if isinstance(name, str) and name.strip():
            updates["name"] = name.strip()
        if updates:
            by_id[str(lid)] = leaf.model_copy(update=updates)
    return list(by_id.values())


def _row_to_leaf(domain: str, row: dict[str, Any]) -> ProficiencyLeafDefinition:
    return ProficiencyLeafDefinition(
        id=str(row["id"]),
        name=str(row.get("name") or ""),
        description=str(row.get("description") or ""),
        domain=str(row.get("domain") or domain),
        stat_weights=dict(row.get("stat_weights") or {}),
        tree_depth=int(row.get("tree_depth") or 0),
        tags=list(row.get("tags") or []),
    )


def leaf_definitions_from_builtin_rows() -> list[ProficiencyLeafDefinition]:
    out: list[ProficiencyLeafDefinition] = []
    for pid, weights in all_builtin_leaf_rows():
        dom = pid.split(".", 1)[0]
        out.append(
            ProficiencyLeafDefinition(
                id=pid,
                name="",
                description="",
                domain=dom,
                stat_weights=weights,
                tree_depth=0,
            )
        )
    return out


def load_proficiency_catalog_from_disk(content_dir: Path) -> ProficiencyCatalogDocument:
    prof_dir = content_dir / "proficiencies"
    catalog_path = prof_dir / "catalog.json"
    overrides_path = prof_dir / "overrides.yaml"

    if catalog_path.is_file():
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        doc = ProficiencyCatalogDocument.model_validate(raw)
        leaves = list(doc.leaves)
    else:
        logger.info("No %s — using builtin proficiency catalog", catalog_path)
        leaves = leaf_definitions_from_builtin_rows()
        doc = ProficiencyCatalogDocument(
            version=1,
            expected_leaf_count=EXPECTED_LEAF_COUNT,
            leaves=leaves,
        )

    if overrides_path.is_file():
        odata = yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or {}
        extra = odata.get("leaves") or []
        by_id = {x.id: x for x in leaves}
        for row in extra:
            if not isinstance(row, dict) or "id" not in row:
                continue
            dom = str(row.get("domain") or row["id"].split(".", 1)[0])
            leaf = _row_to_leaf(dom, row)
            by_id[leaf.id] = leaf
        leaves = list(by_id.values())
        doc = ProficiencyCatalogDocument(
            version=int(doc.version),
            expected_leaf_count=doc.expected_leaf_count,
            leaves=leaves,
        )

    leaves = _merge_leaf_descriptions_overlay(leaves, prof_dir)

    exp = doc.expected_leaf_count
    ok, errs = validate_leaf_definitions(leaves, expected_count=exp)
    if not ok:
        for e in errs:
            logger.error("Proficiency catalog validation: %s", e)
        raise ValueError("proficiency catalog validation failed: " + "; ".join(errs))
    return ProficiencyCatalogDocument(
        version=doc.version,
        expected_leaf_count=exp if exp is not None else len(leaves),
        leaves=leaves,
    )
