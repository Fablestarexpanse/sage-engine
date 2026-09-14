"""Scan on-disk YAML content for the Nexus admin API."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONTENT_WORLD = Path("content/world")
ZONES_ROOT = CONTENT_WORLD / "zones"
ITEMS_DIR = CONTENT_WORLD / "items"


def set_content_root(content_dir: Path) -> None:
    """Point the live content paths at the running world's content directory."""
    global CONTENT_WORLD, ZONES_ROOT, ITEMS_DIR
    root = Path(content_dir)
    CONTENT_WORLD = root / "world"
    ZONES_ROOT = CONTENT_WORLD / "zones"
    ITEMS_DIR = CONTENT_WORLD / "items"


# Parsed YAML by path, reused while the file's mtime and size are unchanged. Listing a big world
# then costs a stat per file, not a parse, so the console can refresh its lists freely.
_YAML_CACHE: dict[Path, tuple[tuple[int, int], dict[str, Any], str | None]] = {}
# libyaml's safe loader is roughly ten times faster than the pure-Python one; same safety rules.
_SAFE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def load_yaml(path: Path) -> tuple[dict[str, Any], str | None]:
    """(data, error) for one content file; data is shared with the cache, so never modify it."""
    try:
        st = path.stat()
    except OSError as e:
        return {}, str(e)
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _YAML_CACHE.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1], hit[2]
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_SAFE_LOADER) or {}
        error = None if isinstance(data, dict) else "not a mapping"
    except Exception as e:
        data, error = {}, str(e).splitlines()[0] if str(e) else type(e).__name__
    if not isinstance(data, dict):
        data = {}
    _YAML_CACHE[path] = (stamp, data, error)
    return data, error


def _is_safe_segment(segment: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", segment))


def list_zone_ids() -> list[str]:
    if not ZONES_ROOT.is_dir():
        return []
    return sorted(p.name for p in ZONES_ROOT.iterdir() if p.is_dir() and _is_safe_segment(p.name))


def zone_summary(zone_id: str) -> dict[str, Any] | None:
    if not _is_safe_segment(zone_id):
        return None
    zpath = ZONES_ROOT / zone_id
    if not zpath.is_dir():
        return None
    rooms_dir = zpath / "rooms"
    room_files = sorted(rooms_dir.glob("*.yaml")) if rooms_dir.is_dir() else []
    meta_path = zpath / "zone.yaml"
    name = zone_id
    ztype = "exploration"
    depth = 0
    status = "active"
    if meta_path.is_file():
        try:
            meta, _ = load_yaml(meta_path)
            name = meta.get("name", zone_id)
            ztype = meta.get("type", ztype)
            dr = meta.get("depth_range") or meta.get("depth")
            if isinstance(dr, list) and dr:
                depth = int(dr[0])
            elif isinstance(dr, int):
                depth = dr
            status = meta.get("status", status)
        except Exception as e:
            logger.debug("zone meta %s: %s", meta_path, e)
    entities = sum(_room_entity_count(rooms_dir / rf.name) for rf in room_files)
    return {
        "id": zone_id,
        "name": name,
        "rooms": len(room_files),
        "entities": entities,
        "players": 0,
        "status": status,
        "type": ztype,
        "depth": depth,
    }


def _room_entity_count(path: Path) -> int:
    data, _ = load_yaml(path)
    spawns = data.get("entity_spawns")
    return len(spawns) if isinstance(spawns, list) else 0


def list_zones() -> list[dict[str, Any]]:
    return [z for z in (zone_summary(zid) for zid in list_zone_ids()) if z]


def room_row(zone_id: str, stem: str, data: dict[str, Any]) -> dict[str, Any]:
    exits = data.get("exits") or {}
    hazards = data.get("hazards") or []
    spawns = data.get("entity_spawns") or []
    features = data.get("features") or []
    rid = data.get("id") or f"{zone_id}:{stem}"
    return {
        "id": rid,
        "name": stem,
        "type": data.get("type", "?"),
        "exits": list(exits.keys()) if isinstance(exits, dict) else [],
        "entities": len(spawns),
        "hazards": len(hazards),
        "features": len(features),
        "depth": data.get("depth", 0),
    }


def list_rooms(zone_id: str) -> list[dict[str, Any]]:
    if not _is_safe_segment(zone_id):
        return []
    rooms_dir = ZONES_ROOT / zone_id / "rooms"
    if not rooms_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for rf in sorted(rooms_dir.glob("*.yaml")):
        data, error = load_yaml(rf)
        if error is None:
            try:
                rows.append(room_row(zone_id, rf.stem, data))
                continue
            except Exception as e:
                error = str(e)
        logger.warning("Skip room %s: %s", rf, error)
        rows.append(
            {
                "id": f"{zone_id}:{rf.stem}",
                "name": rf.stem,
                "type": "?",
                "exits": [],
                "entities": 0,
                "hazards": 0,
                "features": 0,
                "depth": 0,
                "error": error,
            }
        )
    return rows


def aggregate_entity_spawns() -> list[dict[str, Any]]:
    """Roll up entity_spawns.template across all rooms."""
    tally: dict[str, dict[str, Any]] = {}
    for zone_id in list_zone_ids():
        for row in list_rooms(zone_id):
            path = ZONES_ROOT / zone_id / "rooms" / f"{row['name']}.yaml"
            try:
                data, _ = load_yaml(path)
                zone_name = zone_id
                for sp in data.get("entity_spawns") or []:
                    if isinstance(sp, dict):
                        tmpl = str(sp.get("template", "unknown"))
                    else:
                        tmpl = str(sp)
                    key = tmpl
                    if key not in tally:
                        tally[key] = {
                            "id": f"tpl:{tmpl}",
                            "name": tmpl,
                            "type": "spawn",
                            "zone": zone_name,
                            "level": 0,
                            "behavior": "spawn",
                            "status": "active",
                            "count": 0,
                        }
                    tally[key]["count"] += 1
            except Exception as e:
                logger.debug("entity scan %s: %s", path, e)
    return sorted(tally.values(), key=lambda x: x["name"])


def _scan_simple_content_dir(base: Path) -> list[dict[str, Any]]:
    if not base.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for f in sorted(base.glob("*.yaml")):
        data, error = load_yaml(f)
        if error is not None:
            rows.append({"id": f.stem, "name": f.stem, "parse_error": True})
            continue
        rows.append(
            {
                "id": data.get("id", f.stem),
                "name": data.get("name", f.stem),
                **{k: data.get(k) for k in ("type", "rarity", "category", "tier") if k in data},
            }
        )
    return rows


def template_files(kind: str) -> list[tuple[Path, dict[str, Any], str | None]]:
    """(path, data, error) for every entity or item template file, parsed through the cache."""
    if kind not in ("entities", "items"):
        raise ValueError("invalid_kind")
    base = CONTENT_WORLD / kind
    return [(f, *load_yaml(f)) for f in sorted(base.glob("*.yaml"))] if base.is_dir() else []


def list_items() -> list[dict[str, Any]]:
    return _scan_simple_content_dir(ITEMS_DIR)


def list_entity_template_rows() -> list[dict[str, Any]]:
    return _scan_simple_content_dir(CONTENT_WORLD / "entities")


def room_detail(zone_id: str, slug: str) -> dict[str, Any] | None:
    """A room file as text and parsed data (None when the file does not exist)."""
    if not _is_safe_segment(zone_id) or not _is_safe_segment(slug):
        raise ValueError("invalid_slug")
    path = ZONES_ROOT / zone_id / "rooms" / f"{slug}.yaml"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) or {}
        error = None
    except yaml.YAMLError as e:
        data, error = {}, str(e).splitlines()[0]
    return {"id": f"{zone_id}:{slug}", "yaml": text, "data": data, "parse_error": error}


def content_overview() -> dict[str, Any]:
    zones = list_zones()
    total_rooms = sum(z["rooms"] for z in zones)
    spawns = aggregate_entity_spawns()
    spawn_total = sum(int(s.get("count", 0)) for s in spawns)
    return {
        "zones": zones,
        "zone_count": len(zones),
        "room_count": total_rooms,
        "entity_templates": len(list_entity_template_rows()),
        "entity_spawn_references": spawn_total,
        "item_count": len(list_items()),
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".wf_", suffix=path.suffix, dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_room_yaml_text(zone_id: str, room_slug: str, text: str) -> Path:
    """Write raw room YAML through the content seam (validated segments, atomic write)."""
    if not _is_safe_segment(zone_id) or not _is_safe_segment(room_slug):
        raise ValueError("invalid_slug")
    validate_room_yaml_text(zone_id, room_slug, text)
    path = ZONES_ROOT / zone_id / "rooms" / f"{room_slug}.yaml"
    _atomic_write_text(path, text)
    return path


def validate_room_yaml_text(zone_id: str, room_slug: str, text: str) -> None:
    """Refuse room YAML the loader couldn't use; raises ValueError with a short reason."""
    from pydantic import ValidationError

    from sage.world.models import RoomModel

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid_yaml: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("invalid_yaml: top level must be a mapping")
    try:
        room = RoomModel.model_validate(data)
    except ValidationError as e:
        raise ValueError(
            f"invalid_room: {e.error_count()} validation error(s): {e.errors()[0]['loc']} {e.errors()[0]['msg']}"
        ) from None
    if room.id != f"{zone_id}:{room_slug}":
        raise ValueError(f"id_mismatch: expected {zone_id}:{room_slug}, got {room.id}")


def validate_template_yaml_text(kind: str, slug: str, text: str) -> None:
    """Refuse template YAML the loader couldn't use; raises ValueError with a short reason."""
    from pydantic import ValidationError

    from sage.world.models import EntityTemplate, ItemTemplate

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid_yaml: {str(e).splitlines()[0]}") from None
    if not isinstance(data, dict):
        raise ValueError("invalid_yaml: top level must be a mapping")
    model = EntityTemplate if kind == "entities" else ItemTemplate
    try:
        template = model.model_validate(data)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "template"
        raise ValueError(f"invalid_template: {where}: {first['msg']}") from None
    if template.id != slug:
        raise ValueError(f"id_mismatch: expected {slug}, got {template.id}")


def save_template_yaml_text(kind: str, slug: str, text: str) -> Path:
    """Write entity/item template YAML after checking it loads (validated slug, atomic write)."""
    if kind not in ("entities", "items"):
        raise ValueError("invalid_kind")
    if not slug.replace("_", "").isalnum():
        raise ValueError("invalid_slug")
    validate_template_yaml_text(kind, slug, text)
    path = CONTENT_WORLD / kind / f"{slug}.yaml"
    _atomic_write_text(path, text)
    return path
