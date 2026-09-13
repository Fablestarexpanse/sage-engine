"""Scan on-disk YAML content for the Nexus admin API."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONTENT_WORLD = Path("content/world")
ZONES_ROOT = Path("content/world/zones")
ITEMS_DIR = Path("content/world/items")
GLYPHS_DIR = Path("content/world/glyphs")
SYSTEMS_DIR = Path("content/world/systems")
SHIPS_DIR = Path("content/world/ships")
GALAXY_FILE = Path("content/world/galaxy.yaml")
POSITIONS_FILENAME = ".positions.json"
_POSITIONS_DOC_KEYS = frozenset({"version", "positions", "notes", "reference_image", "muted_edges"})


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
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
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
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return len(data.get("entity_spawns") or [])
    except Exception:
        return 0


def list_zones() -> list[dict[str, Any]]:
    return [z for z in (zone_summary(zid) for zid in list_zone_ids()) if z]


def create_zone(zone_id: str, zone_name: str) -> Path:
    """Create ``content/world/zones/{zone_id}/`` with ``zone.yaml`` and starter ``rooms/entrance.yaml``."""
    if not re.match(r"^[a-zA-Z0-9_-]+$", zone_id or ""):
        raise ValueError("invalid_zone_id")
    root = ZONES_ROOT / zone_id
    if root.exists():
        raise FileExistsError("zone_exists")
    rooms_dir = root / "rooms"
    rooms_dir.mkdir(parents=True, exist_ok=True)
    display = (zone_name or "").strip() or zone_id.replace("_", " ").title()
    meta = {"name": display, "type": "exploration", "status": "active"}
    _atomic_write_text(
        root / "zone.yaml",
        yaml.safe_dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
    )
    entrance: dict[str, Any] = {
        "id": f"{zone_id}:entrance",
        "zone": zone_id,
        "type": "hub",
        "depth": 1,
        "description": {"base": f"The entrance to {display}."},
        "exits": {},
        "features": [],
        "entity_spawns": [],
        "tags": [],
    }
    _atomic_write_text(
        rooms_dir / "entrance.yaml",
        yaml.safe_dump(entrance, default_flow_style=False, allow_unicode=True, sort_keys=False),
    )
    return rooms_dir


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
        try:
            with open(rf, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            rows.append(room_row(zone_id, rf.stem, data))
        except Exception as e:
            logger.warning("Skip room %s: %s", rf, e)
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
                    "error": str(e),
                }
            )
    return rows


def get_room_yaml(zone_id: str, room_slug: str) -> str | None:
    if not _is_safe_segment(zone_id) or not _is_safe_segment(room_slug):
        return None
    path = ZONES_ROOT / zone_id / "rooms" / f"{room_slug}.yaml"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def room_file_mtime(zone_id: str, room_slug: str) -> float | None:
    """On-disk mtime for a room YAML, used as an optimistic-concurrency token."""
    if not _is_safe_segment(zone_id) or not _is_safe_segment(room_slug):
        return None
    path = ZONES_ROOT / zone_id / "rooms" / f"{room_slug}.yaml"
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def aggregate_entity_spawns() -> list[dict[str, Any]]:
    """Roll up entity_spawns.template across all rooms."""
    tally: dict[str, dict[str, Any]] = {}
    for zone_id in list_zone_ids():
        for row in list_rooms(zone_id):
            path = ZONES_ROOT / zone_id / "rooms" / f"{row['name']}.yaml"
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
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
        try:
            with open(f, encoding="utf-8") as fp:
                data = yaml.safe_load(fp) or {}
            rows.append(
                {
                    "id": data.get("id", f.stem),
                    "name": data.get("name", f.stem),
                    **{k: data.get(k) for k in ("type", "rarity", "category", "tier") if k in data},
                }
            )
        except Exception:
            rows.append({"id": f.stem, "name": f.stem, "parse_error": True})
    return rows


def list_items() -> list[dict[str, Any]]:
    return _scan_simple_content_dir(ITEMS_DIR)


def list_glyphs() -> list[dict[str, Any]]:
    return _scan_simple_content_dir(GLYPHS_DIR)


def content_overview() -> dict[str, Any]:
    zones = list_zones()
    total_rooms = sum(z["rooms"] for z in zones)
    spawns = aggregate_entity_spawns()
    spawn_total = sum(int(s.get("count", 0)) for s in spawns)
    return {
        "zones": zones,
        "zone_count": len(zones),
        "room_count": total_rooms,
        "entity_templates": len(spawns),
        "entity_spawn_references": spawn_total,
        "item_count": len(list_items()),
        "glyph_count": len(list_glyphs()),
    }


# --- World builder: zone graph, positions sidecar, room CRUD -----------------


def _positions_path(zone_id: str) -> Path:
    return ZONES_ROOT / zone_id / POSITIONS_FILENAME


def _load_positions_raw(zone_id: str) -> dict[str, Any]:
    p = _positions_path(zone_id)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("positions %s: %s", p, e)
        return {}


def load_zone_positions(zone_id: str) -> dict[str, dict[str, float]]:
    """Room slug -> {x, y} for layout. Supports legacy flat JSON and v2 wrapped format."""
    data = _load_positions_raw(zone_id)
    if not data:
        return {}
    out: dict[str, dict[str, float]] = {}
    if data.get("version") == 2 and isinstance(data.get("positions"), dict):
        for k, v in data["positions"].items():
            if isinstance(v, dict) and "x" in v and "y" in v:
                out[str(k)] = {"x": float(v["x"]), "y": float(v["y"])}
        return out
    for k, v in data.items():
        if k in _POSITIONS_DOC_KEYS:
            continue
        if isinstance(v, dict) and "x" in v and "y" in v:
            out[str(k)] = {"x": float(v["x"]), "y": float(v["y"])}
    return out


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

    from fablestar.world.models import RoomModel

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


def save_template_yaml_text(kind: str, slug: str, text: str) -> Path:
    """Write raw entity/item template YAML (validated slug, atomic write)."""
    if kind not in ("entities", "items"):
        raise ValueError("invalid_kind")
    if not slug.replace("_", "").isalnum():
        raise ValueError("invalid_slug")
    path = CONTENT_WORLD / kind / f"{slug}.yaml"
    _atomic_write_text(path, text)
    return path


def _atomic_write_json(path: Path, obj: Any) -> None:
    _atomic_write_text(path, json.dumps(obj, indent=2))


def _atomic_write_yaml(path: Path, data: Any) -> None:
    _atomic_write_text(
        path,
        yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
    )


def save_zone_positions(zone_id: str, positions: dict[str, Any]) -> str:
    """Map room slug -> {x, y}. Merges into v2 .positions.json; preserves WorldForge metadata."""
    if not _is_safe_segment(zone_id):
        raise ValueError("invalid_zone")
    zpath = ZONES_ROOT / zone_id
    if not zpath.is_dir():
        raise ValueError("zone_not_found")
    existing = _load_positions_raw(zone_id)

    pos_full: dict[str, dict[str, Any]] = {}
    if existing.get("version") == 2 and isinstance(existing.get("positions"), dict):
        for k, v in existing["positions"].items():
            if isinstance(v, dict) and "x" in v and "y" in v:
                pos_full[str(k)] = dict(v)
    else:
        for k, v in existing.items():
            if k in _POSITIONS_DOC_KEYS:
                continue
            if isinstance(v, dict) and "x" in v and "y" in v:
                pos_full[str(k)] = dict(v)

    authoritative: dict[str, dict[str, Any]] = {}
    for k, v in (positions or {}).items():
        if not _is_safe_segment(str(k)):
            continue
        if isinstance(v, dict):
            authoritative[str(k)] = v

    pos_merged: dict[str, dict[str, Any]] = {}
    for k, v in authoritative.items():
        prev = pos_full.get(k, {})
        entry: dict[str, Any] = dict(prev) if isinstance(prev, dict) else {}
        entry["x"] = float(v.get("x", 0))
        entry["y"] = float(v.get("y", 0))
        pos_merged[k] = entry

    notes = existing.get("notes")
    if not isinstance(notes, list):
        notes = []
    muted = existing.get("muted_edges")
    if not isinstance(muted, list):
        muted = []
    ref_img = existing.get("reference_image")
    out_doc: dict[str, Any] = {
        "version": 2,
        "positions": pos_merged,
        "notes": notes,
        "muted_edges": muted,
    }
    if isinstance(ref_img, dict):
        out_doc["reference_image"] = ref_img

    p = _positions_path(zone_id)
    _atomic_write_json(p, out_doc)
    return str(p)


def _resolve_exit_destination(zone_id: str, dest: str, known_ids: set[str]) -> str | None:
    if not dest or not isinstance(dest, str):
        return None
    d = dest.strip()
    if d.startswith("self:") or d.startswith("@") or not d:
        return None
    if ":" in d:
        return d if d in known_ids else None
    cand = f"{zone_id}:{d}"
    return cand if cand in known_ids else None


def _opposite_dir(direction: str) -> str | None:
    """Opposite cardinal direction, or None for non-cardinal exits.

    None (rather than a fabricated default) lets React Flow attach the edge to
    the node body instead of silently pinning unknown directions to one side.
    """
    return {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "up": "down",
        "down": "up",
    }.get(str(direction).lower())


def _exit_edge(
    source_id: str,
    direction: str,
    target_id: str,
    description: str,
    *,
    one_way: bool | None = None,
) -> dict[str, Any]:
    """Shared React Flow edge shape for zone_graph and ship_graph."""
    dlow = str(direction).lower()
    data: dict[str, Any] = {"direction": str(direction), "description": description}
    if one_way is not None:
        data["oneWay"] = one_way
    return {
        "id": f"{source_id}|{direction}|{target_id}",
        "source": source_id,
        "target": target_id,
        "sourceHandle": dlow,
        "targetHandle": _opposite_dir(dlow),
        "type": "exit",
        "label": str(direction),
        "data": data,
    }


def _load_zone_rooms(
    rooms_dir: Path,
    warnings: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, float | None]]:
    """Load every room YAML in a zone: (data by slug, on-disk mtime by slug)."""
    room_data_by_slug: dict[str, dict[str, Any]] = {}
    room_mtime_by_slug: dict[str, float | None] = {}
    for rf in sorted(rooms_dir.glob("*.yaml")):
        slug = rf.stem
        try:
            room_mtime_by_slug[slug] = rf.stat().st_mtime
        except OSError:
            room_mtime_by_slug[slug] = None
        try:
            with open(rf, encoding="utf-8") as f:
                room_data_by_slug[slug] = yaml.safe_load(f) or {}
        except Exception as e:
            warnings.append(f"parse_error:{slug}:{e}")
            room_data_by_slug[slug] = {}
    return room_data_by_slug, room_mtime_by_slug


def zone_graph(zone_id: str) -> dict[str, Any]:
    if not _is_safe_segment(zone_id):
        return {"nodes": [], "edges": [], "warnings": ["invalid_zone"], "external_exits": []}
    rooms_dir = ZONES_ROOT / zone_id / "rooms"
    if not rooms_dir.is_dir():
        return {"nodes": [], "edges": [], "warnings": ["no_rooms_dir"], "external_exits": []}

    positions = load_zone_positions(zone_id)
    warnings: list[str] = []
    external_exits: list[dict[str, Any]] = []
    room_data_by_slug, room_mtime_by_slug = _load_zone_rooms(rooms_dir, warnings)

    known_ids: set[str] = set()
    for slug, data in room_data_by_slug.items():
        rid = data.get("id") or f"{zone_id}:{slug}"
        known_ids.add(str(rid))

    nodes: list[dict[str, Any]] = []
    for i, (slug, data) in enumerate(sorted(room_data_by_slug.items())):
        rid = str(data.get("id") or f"{zone_id}:{slug}")
        pos = positions.get(slug, {"x": float((i % 6) * 220), "y": float((i // 6) * 120)})
        desc = data.get("description") or {}
        if isinstance(desc, dict):
            has_desc = bool(str(desc.get("base", "")).strip())
        else:
            has_desc = bool(str(desc).strip())
        exits = data.get("exits") or {}
        if not isinstance(exits, dict):
            exits = {}
        spawns = data.get("entity_spawns") or []
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            tags = list(tags) if hasattr(tags, "__iter__") else []

        nodes.append(
            {
                "id": rid,
                "type": "room",
                "position": {"x": float(pos["x"]), "y": float(pos["y"])},
                "data": {
                    "slug": slug,
                    "label": slug,
                    "roomId": rid,
                    "roomType": data.get("type", "?"),
                    "depth": data.get("depth", 0),
                    "group": data.get("group"),
                    "hasDescription": has_desc,
                    "entityCount": len(spawns) if isinstance(spawns, list) else 0,
                    "exitCount": len(exits),
                    "tags": tags,
                    "raw": data,
                    # Optimistic-concurrency token: echo back as expected_mtime on room writes.
                    "mtime": room_mtime_by_slug.get(slug),
                },
            }
        )

    edges: list[dict[str, Any]] = []
    edge_ids_used: set[str] = set()
    for slug, data in room_data_by_slug.items():
        source_id = str(data.get("id") or f"{zone_id}:{slug}")
        exits = data.get("exits") or {}
        if not isinstance(exits, dict):
            continue
        for direction, ex in exits.items():
            if not isinstance(ex, dict):
                continue
            dest = ex.get("destination", "")
            target_id = _resolve_exit_destination(zone_id, str(dest), known_ids)
            edesc = str(ex.get("description", ""))
            if target_id:
                eid = f"{source_id}|{direction}|{target_id}"
                if eid in edge_ids_used:
                    continue
                edge_ids_used.add(eid)
                one_way = bool(ex.get("one_way")) if isinstance(ex, dict) else False
                edges.append(
                    _exit_edge(source_id, str(direction), target_id, edesc, one_way=one_way)
                )
            else:
                external_exits.append(
                    {
                        "from": source_id,
                        "direction": str(direction),
                        "destination": str(dest),
                        "description": edesc,
                    }
                )

    return {"nodes": nodes, "edges": edges, "warnings": warnings, "external_exits": external_exits}


def _deep_merge_room(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def save_room_dict(zone_id: str, room_slug: str, data: dict[str, Any]) -> Path:
    if not _is_safe_segment(zone_id) or not _is_safe_segment(room_slug):
        raise ValueError("invalid_slug")
    path = ZONES_ROOT / zone_id / "rooms" / f"{room_slug}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(
                "save_room_dict: could not parse existing %s (%s); merging onto empty", path, e
            )
            existing = {}
    merged = _deep_merge_room(existing, data)
    merged["id"] = merged.get("id") or f"{zone_id}:{room_slug}"
    merged["zone"] = zone_id
    text = yaml.safe_dump(merged, default_flow_style=False, allow_unicode=True, sort_keys=False)
    _atomic_write_text(path, text)
    return path


def create_room(zone_id: str, slug: str, initial: dict[str, Any] | None = None) -> Path:
    if not _is_safe_segment(zone_id) or not _is_safe_segment(slug):
        raise ValueError("invalid_slug")
    path = ZONES_ROOT / zone_id / "rooms" / f"{slug}.yaml"
    if path.is_file():
        raise FileExistsError("room_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    base: dict[str, Any] = {
        "id": f"{zone_id}:{slug}",
        "zone": zone_id,
        "type": "chamber",
        "depth": 1,
        "description": {"base": ""},
        "exits": {},
        "features": [],
        "entity_spawns": [],
        "tags": [],
    }
    if initial:
        base = _deep_merge_room(base, initial)
    base["id"] = f"{zone_id}:{slug}"
    base["zone"] = zone_id
    text = yaml.safe_dump(base, default_flow_style=False, allow_unicode=True, sort_keys=False)
    _atomic_write_text(path, text)
    return path


def delete_room(zone_id: str, room_slug: str) -> None:
    if not _is_safe_segment(zone_id) or not _is_safe_segment(room_slug):
        raise ValueError("invalid_slug")
    path = ZONES_ROOT / zone_id / "rooms" / f"{room_slug}.yaml"
    if not path.is_file():
        raise FileNotFoundError("not_found")
    path.unlink()
    pos = load_zone_positions(zone_id)
    if room_slug in pos:
        del pos[room_slug]
        save_zone_positions(zone_id, pos)


# --- Galaxy / systems / ships (builder) ---------------------------------------
# galaxy.yaml lists systems by id + filename under content/world/systems/ — no $ref resolver in v1.


def galaxy_overview() -> dict[str, Any]:
    systems_out: list[dict[str, Any]] = []
    if GALAXY_FILE.is_file():
        try:
            with open(GALAXY_FILE, encoding="utf-8") as f:
                gal = yaml.safe_load(f) or {}
            g = gal.get("galaxy") or gal
            raw_list = g.get("systems") or []
            for entry in raw_list:
                if isinstance(entry, str):
                    sid = entry.replace(".yaml", "")
                    systems_out.append({"id": sid, "file": f"{sid}.yaml"})
                elif isinstance(entry, dict):
                    raw_sid = entry.get("id") or entry.get("system_id")
                    fn = entry.get("file") or f"{raw_sid}.yaml"
                    if raw_sid:
                        systems_out.append({"id": str(raw_sid), "file": str(fn)})
        except Exception as e:
            logger.warning("galaxy.yaml: %s", e)
    if not systems_out and SYSTEMS_DIR.is_dir():
        for sys_path in sorted(SYSTEMS_DIR.glob("*.yaml")):
            systems_out.append({"id": sys_path.stem, "file": sys_path.name})

    details: list[dict[str, Any]] = []
    for s in systems_out:
        sid = s["id"]
        d = system_detail(sid)
        if d:
            details.append(d)
        else:
            details.append({"id": sid, "error": "missing_file"})

    return {"galaxy_id": "fablestar", "systems": details}


def system_detail(system_id: str) -> dict[str, Any] | None:
    if not _is_safe_segment(system_id):
        return None
    path = SYSTEMS_DIR / f"{system_id}.yaml"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("system_detail: could not parse %s: %s", path, e)
        return None
    sys_block = data.get("system") or data
    return {
        "id": sys_block.get("id", system_id),
        "name": sys_block.get("name", system_id),
        "coordinates": sys_block.get("coordinates") or {"x": 0, "y": 0, "z": 0},
        "star": sys_block.get("star") or {},
        "faction": sys_block.get("faction", "neutral"),
        "security": sys_block.get("security", "low"),
        "connections": sys_block.get("connections") or [],
        "bodies": sys_block.get("bodies") or [],
        "raw": data,
    }


def _search_category(
    label: str,
    rows: Callable[[], Any],
    hit: Callable[[dict[str, Any]], dict[str, Any] | None],
    cap: int,
) -> list[dict[str, Any]]:
    """Collect up to `cap` matches from a category, logging (not swallowing) failures."""
    found: list[dict[str, Any]] = []
    try:
        for row in rows():
            h = hit(row)
            if h is not None:
                found.append(h)
                if len(found) >= cap:
                    break
    except Exception as e:
        logger.debug("builder_search %s: %s", label, e)
    return found


def builder_search(query: str, limit: int = 30) -> dict[str, list[dict[str, Any]]]:
    """Lightweight cross-content search for the World Builder (prefix/substring match)."""
    q = (query or "").strip().lower()
    out: dict[str, list[dict[str, Any]]] = {"zones": [], "systems": [], "ships": [], "rooms": []}
    if not q or limit < 1:
        return out
    per_cat = max(3, min(limit // 4, 20))

    def zone_hit(row: dict[str, Any]) -> dict[str, Any] | None:
        nid, name = str(row.get("id", "")), str(row.get("name", ""))
        if q not in nid.lower() and q not in name.lower():
            return None
        return {
            "kind": "zone",
            "id": nid,
            "label": name or nid,
            "detail": f"{row.get('type', '')} · {row.get('rooms', 0)} rooms",
        }

    def system_hit(s: dict[str, Any]) -> dict[str, Any] | None:
        if s.get("error"):
            return None
        sid, name, fac = str(s.get("id", "")), str(s.get("name", "")), str(s.get("faction", ""))
        if q not in sid.lower() and q not in name.lower() and q not in fac.lower():
            return None
        return {"kind": "system", "id": sid, "label": name or sid, "detail": fac or "—"}

    def ship_hit(sh: dict[str, Any]) -> dict[str, Any] | None:
        sid, name = str(sh.get("id", "")), str(sh.get("name", ""))
        if q not in sid.lower() and q not in name.lower():
            return None
        return {"kind": "ship", "id": sid, "label": name or sid, "detail": str(sh.get("size", ""))}

    out["zones"] = _search_category("zones", list_zones, zone_hit, per_cat)
    out["systems"] = _search_category(
        "systems", lambda: galaxy_overview().get("systems") or [], system_hit, per_cat
    )
    out["ships"] = _search_category("ships", list_ship_templates, ship_hit, per_cat)

    def all_rooms() -> Any:
        for zid in list_zone_ids():
            try:
                rows = list_rooms(zid)
            except Exception as e:
                logger.debug("builder_search rooms zone %s: %s", zid, e)
                continue
            for row in rows:
                yield zid, row

    def room_hit(pair: tuple[str, dict[str, Any]]) -> dict[str, Any] | None:
        zid, row = pair
        stem, rid = str(row.get("name", "")), str(row.get("id", ""))
        if q not in f"{stem} {rid} {zid}".lower():
            return None
        return {
            "kind": "room",
            "zone_id": zid,
            "room_slug": stem,
            "label": rid if ":" in rid else f"{zid}:{stem}",
            "detail": f"type {row.get('type', '?')}",
        }

    out["rooms"] = _search_category("rooms", all_rooms, room_hit, min(per_cat * 2, 40))
    return out


def ensure_system_in_galaxy_index(system_id: str, filename: str | None = None) -> None:
    """Append system id to galaxy.yaml if missing."""
    if not _is_safe_segment(system_id):
        raise ValueError("invalid_system_id")
    fn = filename or f"{system_id}.yaml"
    gal_root: dict[str, Any] = {}
    if GALAXY_FILE.is_file():
        try:
            with open(GALAXY_FILE, encoding="utf-8") as f:
                gal_root = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("galaxy read: %s", e)
            gal_root = {}
    g = gal_root.get("galaxy")
    if not isinstance(g, dict):
        g = {"id": "fablestar_galaxy", "name": "Galaxy", "systems": []}
        gal_root["galaxy"] = g
    systems_list = g.get("systems")
    if not isinstance(systems_list, list):
        systems_list = []
        g["systems"] = systems_list
    for entry in systems_list:
        if isinstance(entry, dict) and str(entry.get("id")) == system_id:
            return
        if isinstance(entry, str) and entry.replace(".yaml", "") == system_id:
            return
    systems_list.append({"id": system_id, "file": fn})
    _atomic_write_yaml(GALAXY_FILE, gal_root)


def save_system_document(system_id: str, document: dict[str, Any]) -> Path:
    """Overwrite systems/{system_id}.yaml with document (must include a top-level `system` dict)."""
    if not _is_safe_segment(system_id):
        raise ValueError("invalid_system_id")
    if not isinstance(document, dict) or not isinstance(document.get("system"), dict):
        raise ValueError("document_must_have_system_key")
    path = SYSTEMS_DIR / f"{system_id}.yaml"
    sys_block = document["system"]
    if str(sys_block.get("id", system_id)) != system_id:
        sys_block["id"] = system_id
    _atomic_write_yaml(path, document)
    return path


def create_system(
    system_id: str,
    name: str,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    faction: str = "neutral",
    security: str = "low",
    star_type: str = "G2V",
    star_name: str = "",
    add_to_galaxy: bool = True,
) -> Path:
    if not _is_safe_segment(system_id):
        raise ValueError("invalid_system_id")
    path = SYSTEMS_DIR / f"{system_id}.yaml"
    if path.is_file():
        raise FileExistsError("system_exists")
    display = name.strip() or system_id.replace("_", " ").title()
    sn = star_name.strip() or f"{display} Star"
    doc = {
        "system": {
            "id": system_id,
            "name": display,
            "coordinates": {"x": float(x), "y": float(y), "z": float(z)},
            "star": {"type": star_type, "name": sn},
            "faction": faction,
            "security": security,
            "connections": [],
            "bodies": [],
        }
    }
    _atomic_write_yaml(path, doc)
    if add_to_galaxy:
        ensure_system_in_galaxy_index(system_id)
    return path


def create_ship_template(ship_id: str, name: str, size: str = "small") -> Path:
    if not _is_safe_segment(ship_id):
        raise ValueError("invalid_ship_id")
    path = SHIPS_DIR / f"{ship_id}.yaml"
    if path.is_file():
        raise FileExistsError("ship_exists")
    display = name.strip() or ship_id.replace("_", " ").title()
    doc = {"ship": {"id": ship_id, "name": display, "size": size, "rooms": []}}
    _atomic_write_yaml(path, doc)
    return path


def list_ship_templates() -> list[dict[str, Any]]:
    if not SHIPS_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(SHIPS_DIR.glob("*.yaml")):
        if not _is_safe_segment(f.stem):
            continue
        try:
            with open(f, encoding="utf-8") as fp:
                data = yaml.safe_load(fp) or {}
            ship = data.get("ship") or data
            out.append(
                {
                    "id": ship.get("id", f.stem),
                    "name": ship.get("name", f.stem),
                    "size": ship.get("size", "small"),
                }
            )
        except Exception:
            out.append({"id": f.stem, "name": f.stem, "parse_error": True})
    return out


def ship_graph(ship_id: str) -> dict[str, Any]:
    """React Flow graph from content/world/ships/{ship_id}.yaml (ship.rooms list)."""
    if not _is_safe_segment(ship_id):
        return {
            "nodes": [],
            "edges": [],
            "warnings": ["invalid_ship"],
            "external_exits": [],
            "ship": None,
        }
    path = SHIPS_DIR / f"{ship_id}.yaml"
    if not path.is_file():
        return {
            "nodes": [],
            "edges": [],
            "warnings": ["not_found"],
            "external_exits": [],
            "ship": None,
        }
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return {"nodes": [], "edges": [], "warnings": [str(e)], "external_exits": [], "ship": None}

    ship = data.get("ship") or data
    rooms = ship.get("rooms") or []
    if not isinstance(rooms, list):
        return {
            "nodes": [],
            "edges": [],
            "warnings": ["no_rooms"],
            "external_exits": [],
            "ship": None,
        }

    prefix = f"ship:{ship_id}:"
    known: set[str] = set()
    for r in rooms:
        if isinstance(r, dict) and r.get("id"):
            known.add(prefix + str(r["id"]))

    nodes: list[dict[str, Any]] = []
    for i, r in enumerate(rooms):
        if not isinstance(r, dict) or not r.get("id"):
            continue
        rid = prefix + str(r["id"])
        nodes.append(
            {
                "id": rid,
                "type": "room",
                "position": {"x": float((i % 5) * 200), "y": float((i // 5) * 100)},
                "data": {
                    "slug": str(r["id"]),
                    "label": r.get("name", r["id"]),
                    "roomId": rid,
                    "roomType": r.get("type", "?"),
                    "depth": 0,
                    "hasDescription": bool(
                        (r.get("description") or {}).get("base", "")
                        if isinstance(r.get("description"), dict)
                        else r.get("description")
                    ),
                    "entityCount": 0,
                    "exitCount": len(r.get("exits") or {})
                    if isinstance(r.get("exits"), dict)
                    else 0,
                    "tags": [],
                    "raw": r,
                    "shipId": ship_id,
                },
            }
        )

    edges: list[dict[str, Any]] = []
    external: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rooms:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        source_id = prefix + str(r["id"])
        exits = r.get("exits") or {}
        if not isinstance(exits, dict):
            continue
        for direction, ex in exits.items():
            if not isinstance(ex, dict):
                continue
            dest = str(ex.get("destination", ""))
            target_id: str | None = None
            if dest.startswith("self:"):
                tail = dest.split(":", 1)[1]
                cand = prefix + tail
                if cand in known:
                    target_id = cand
            elif dest in known:
                target_id = dest
            edesc = str(ex.get("description", ""))
            if target_id:
                eid = f"{source_id}|{direction}|{target_id}"
                if eid not in seen:
                    seen.add(eid)
                    edges.append(_exit_edge(source_id, str(direction), target_id, edesc))
            else:
                external.append(
                    {
                        "from": source_id,
                        "direction": str(direction),
                        "destination": dest,
                        "description": edesc,
                    }
                )

    return {
        "nodes": nodes,
        "edges": edges,
        "warnings": [],
        "external_exits": external,
        "ship": ship,
    }


def save_ship_room(ship_id: str, room_local_id: str, patch: dict[str, Any]) -> Path:
    """Merge patch into one entry in ship.rooms[] matching id."""
    if not _is_safe_segment(ship_id) or not _is_safe_segment(room_local_id):
        raise ValueError("invalid_slug")
    path = SHIPS_DIR / f"{ship_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError("ship_not_found")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    ship: dict[str, Any] = data["ship"] if isinstance(data.get("ship"), dict) else data
    rooms = list(ship.get("rooms") or [])
    found = False
    for i, r in enumerate(rooms):
        if isinstance(r, dict) and str(r.get("id")) == room_local_id:
            rooms[i] = _deep_merge_room(dict(r), patch)
            found = True
            break
    if not found:
        raise ValueError("room_not_found")
    ship["rooms"] = rooms
    text = yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    _atomic_write_text(path, text)
    return path


PROFICIENCIES_CATALOG_JSON = Path("content/proficiencies/catalog.json")


def read_proficiency_catalog_document() -> dict[str, Any]:
    """Return raw ``catalog.json`` (version, expected_leaf_count, leaves) for admin editing."""
    if not PROFICIENCIES_CATALOG_JSON.is_file():
        raise FileNotFoundError("proficiency_catalog_missing")
    raw = json.loads(PROFICIENCIES_CATALOG_JSON.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("invalid_catalog_root")
    return raw


def write_proficiency_catalog_document(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and atomically write ``content/proficiencies/catalog.json``.
    ``expected_leaf_count`` is forced to ``len(leaves)`` so it stays consistent.
    """
    from fablestar.proficiencies.models import ProficiencyCatalogDocument
    from fablestar.proficiencies.validation import validate_leaf_definitions

    if not isinstance(raw, dict):
        raise ValueError("catalog_must_be_object")
    leaves_in = raw.get("leaves")
    if not isinstance(leaves_in, list):
        raise ValueError("leaves_must_be_array")
    version = int(raw.get("version") or 1)
    n = len(leaves_in)
    doc_dict = {"version": version, "expected_leaf_count": n, "leaves": leaves_in}
    try:
        doc = ProficiencyCatalogDocument.model_validate(doc_dict)
    except Exception as e:
        raise ValueError(f"catalog_schema: {e}") from e
    ok, errs = validate_leaf_definitions(list(doc.leaves), expected_count=len(doc.leaves))
    if not ok:
        raise ValueError("; ".join(errs))
    payload = doc.model_dump(mode="json")
    _atomic_write_json(PROFICIENCIES_CATALOG_JSON, payload)
    return {
        "ok": True,
        "leaf_count": len(doc.leaves),
        "path": str(PROFICIENCIES_CATALOG_JSON.resolve()),
    }
