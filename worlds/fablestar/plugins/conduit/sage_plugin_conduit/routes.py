"""Conduit HTTP routes: the admin catalog editor."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from sage.api import PluginAPI

from .models import ProficiencyCatalogDocument
from .validation import validate_leaf_definitions


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def mount(api: PluginAPI, catalog: Any) -> None:
    catalog_json = Path(api.world.content_dir) / "proficiencies" / "catalog.json"

    admin = APIRouter()

    @admin.get("/catalog")
    async def catalog_get():
        """Raw catalog.json (version, expected_leaf_count, leaves) for editing."""
        if not catalog_json.is_file():
            raise HTTPException(status_code=404, detail="proficiency_catalog_missing")
        raw = json.loads(catalog_json.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise HTTPException(status_code=500, detail="invalid_catalog_root")
        return raw

    @admin.put("/catalog")
    async def catalog_put(body: dict[str, Any] = Body(...)):
        """Validate and atomically write catalog.json; expected_leaf_count follows the leaves."""
        leaves_in = body.get("leaves") if isinstance(body, dict) else None
        if not isinstance(leaves_in, list):
            raise HTTPException(status_code=400, detail="leaves_must_be_array")
        doc_dict = {
            "version": int(body.get("version") or 1),
            "expected_leaf_count": len(leaves_in),
            "leaves": leaves_in,
        }
        try:
            doc = ProficiencyCatalogDocument.model_validate(doc_dict)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"catalog_schema: {exc}") from exc
        ok, errs = validate_leaf_definitions(list(doc.leaves), expected_count=len(doc.leaves))
        if not ok:
            raise HTTPException(status_code=400, detail="; ".join(errs))
        _atomic_write_json(catalog_json, doc.model_dump(mode="json"))
        # The registry reloads on the file change (content cache), no restart.
        return {"ok": True, "leaf_count": len(doc.leaves), "path": str(catalog_json)}

    api.http.admin_router(admin, tool="skills")
