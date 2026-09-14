"""Entity and item templates as a searchable, sortable, paged table for the admin console.

Columns come from the template model plus the fields loaded plugins add (``content.schema.json``),
so a world's own fields (a combat plugin's ``attack``, a crafting plugin's ``recipe``) appear
without console code knowing about them. Creature ``stats`` keys become one column each.
"""

from __future__ import annotations

from typing import Any

from sage.admin import content_browser
from sage.world.models import EntityTemplate, ItemTemplate

KINDS = {"items": ("item", ItemTemplate), "entities": ("entity", EntityTemplate)}
_NOT_COLUMNS = {"id", "name", "description"}
SORT_FIRST = ("name", "id")


def _column_kind(schema: dict[str, Any]) -> str:
    options = schema.get("anyOf") or [schema]
    types = [o.get("type") for o in options if o.get("type") not in (None, "null")]
    kind = types[0] if types else schema.get("type")
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "bool"
    if kind in ("array", "object"):
        return "count"
    return "text"


def columns(kind: str, extension_schemas: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict]:
    model_name, model = KINDS[kind]
    cols: list[dict[str, Any]] = []
    props = model.model_json_schema().get("properties", {})
    for key, schema in props.items():
        if key in _NOT_COLUMNS or key == "stats":
            continue
        col_kind = "tags" if key == "tags" else _column_kind(schema)
        cols.append(
            {"key": key, "label": schema.get("title", key), "kind": col_kind, "owner": None}
        )
    if "stats" in props:
        stat_keys = sorted({k for r in rows for k in (r.get("stats") or {}) if isinstance(k, str)})
        cols += [
            {"key": f"stats.{k}", "label": k, "kind": "number", "owner": None} for k in stat_keys
        ]
    prefix = f"{model_name}."
    for name in sorted(extension_schemas):
        if not name.startswith(prefix):
            continue
        entry = extension_schemas[name] or {}
        schema = entry.get("schema", {})
        field = name[len(prefix) :]
        cols.append(
            {
                "key": field,
                # Extension titles are often shared ("Bonus" for attack and defense): use the field.
                "label": field,
                "kind": _column_kind(schema),
                "owner": entry.get("owner"),
            }
        )
    # A type column first: it is the filter staff reach for.
    cols.sort(key=lambda c: c["key"] != "type")
    return cols


def _value(data: dict[str, Any], col: dict[str, Any]) -> Any:
    if col["key"].startswith("stats."):
        stats = data.get("stats")
        raw = stats.get(col["key"][6:]) if isinstance(stats, dict) else None
    else:
        raw = data.get(col["key"])
    if raw is None:
        return None
    if col["kind"] == "count":
        return len(raw) if isinstance(raw, list | dict) else None
    if col["kind"] == "tags":
        return sorted(str(t) for t in raw) if isinstance(raw, list) else None
    if col["kind"] == "number":
        return raw if isinstance(raw, int | float) and not isinstance(raw, bool) else None
    return raw if isinstance(raw, str | bool) else str(raw)


def table(
    kind: str,
    extension_schemas: dict[str, Any],
    *,
    q: str = "",
    type_: str = "",
    sort: str = "name",
    desc: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError("invalid_kind")
    files = content_browser.template_files(kind)
    datas = [data for _, data, error in files if error is None]
    cols = columns(kind, extension_schemas, datas)
    rows = []
    for path, data, error in files:
        values = {} if error else {c["key"]: _value(data, c) for c in cols}
        rows.append(
            {
                "id": str(data.get("id", path.stem)) if not error else path.stem,
                "name": str(data.get("name", path.stem)) if not error else path.stem,
                "parse_error": error,
                "values": values,
            }
        )
    types = sorted({str(r["values"]["type"]) for r in rows if r["values"].get("type")})

    needle = (q or "").strip().lower()
    if needle:
        rows = [
            r
            for r in rows
            if needle in r["id"].lower()
            or needle in r["name"].lower()
            or any(needle in t.lower() for t in r["values"].get("tags") or [])
        ]
    if type_:
        rows = [r for r in rows if r["values"].get("type") == type_]

    if sort in SORT_FIRST or any(c["key"] == sort for c in cols):

        def pick(r: dict[str, Any]) -> Any:
            return r[sort] if sort in SORT_FIRST else r["values"].get(sort)

        # Rows without a value stay at the bottom in either direction.
        present = sorted(
            (r for r in rows if pick(r) is not None),
            key=lambda r: _comparable(pick(r)),
            reverse=desc,
        )
        rows = present + [r for r in rows if pick(r) is None]
    total = len(rows)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    return {
        "rows": rows[offset : offset + limit],
        "total": total,
        "columns": cols,
        "types": types,
    }


def _comparable(v: Any) -> tuple:
    if isinstance(v, list):
        return (0, len(v), "")
    if isinstance(v, bool):
        return (0, int(v), "")
    if isinstance(v, int | float):
        return (0, v, "")
    return (1, 0, str(v).lower())
