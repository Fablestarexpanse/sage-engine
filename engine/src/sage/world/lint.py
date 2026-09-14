"""Static checks of a world's content (no server, no database): one validator for every tool.

Used by tests, the `sage validate` CLI and worldforge-mcp's `validate_zone` (PHASE1_CONTRACTS
D.E). Three levels:

- errors break play: a room that fails its schema or has the wrong id, an exit to a room that
  does not exist or to itself, a spawn or loot row naming a missing template, a start or respawn
  room that is not there, and room types or exit directions the world's `world.toml` does not
  declare (when it declares any);
- warnings are map smells: a two-way exit whose far side does not lead back, a room or feature
  without a description, a room with no exits or cut off from the rest of its zone, and a zone
  with less than 0.5 gameplay draws per room;
- info is context: one-way and cross-zone exits, dead ends, depth jumps, feature density.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from sage.world.models import EntityTemplate, ItemTemplate, RoomModel

OPPOSITE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "down",
    "down": "up",
    "northeast": "southwest",
    "southwest": "northeast",
    "northwest": "southeast",
    "southeast": "northwest",
}
DENSITY_TARGET = 0.5


@dataclass
class LintReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    rooms: dict[str, RoomModel] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "info": list(self.info),
            "counts": {"err": len(self.errors), "warn": len(self.warnings)},
        }


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _first_line(exc: Exception) -> str:
    return str(exc).splitlines()[0]


def _templates(directory: Path, model: type, report: LintReport) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in sorted(directory.glob("*.yaml")) if directory.is_dir() else []:
        try:
            doc = model(**_load(path))
        except (ValidationError, TypeError, yaml.YAMLError) as exc:
            report.errors.append(f"{directory.name}/{path.name}: {_first_line(exc)}")
            continue
        out[doc.id] = doc
    return out


def lint_content(
    world_dir: Path | str,
    *,
    room_types: Iterable[str] = (),
    exit_dirs: Iterable[str] = (),
    required_rooms: Iterable[str] = (),
    zone: str | None = None,
) -> LintReport:
    """Check a `content/world` directory. With `zone`, room-level findings cover that zone only
    (exits into other zones still resolve against every room)."""
    report = LintReport()
    base = Path(world_dir)
    room_types, exit_dirs = set(room_types), set(exit_dirs)

    for path in sorted((base / "zones").glob("*/rooms/*.yaml")):
        zone_id = path.parent.parent.name
        try:
            room = RoomModel(**_load(path))
        except (ValidationError, TypeError, yaml.YAMLError) as exc:
            if zone in (None, zone_id):
                report.errors.append(f"{zone_id}/{path.name}: {_first_line(exc)}")
            continue
        if room.id != f"{zone_id}:{path.stem}" and zone in (None, zone_id):
            report.errors.append(
                f"{zone_id}/{path.name}: id {room.id!r} should be {zone_id}:{path.stem}"
            )
        report.rooms[room.id] = room

    entities = _templates(base / "entities", EntityTemplate, report)
    items = _templates(base / "items", ItemTemplate, report)

    for room_id in required_rooms:
        if room_id not in report.rooms:
            report.errors.append(f"world.toml names room {room_id!r}, which does not exist")

    checked = {rid: r for rid, r in report.rooms.items() if zone in (None, r.zone)}
    if zone is not None and not checked:
        report.errors.append(f"zone {zone!r} has no rooms")
        return report

    for room_id, room in sorted(checked.items()):
        if room_types and room.type not in room_types:
            report.errors.append(f"{room_id}: room type {room.type!r} is not in world.toml")
        if not str(room.description.get("base", "")).strip():
            report.warnings.append(f"{room_id}: missing description")
        if not room.exits and len([r for r in report.rooms.values() if r.zone == room.zone]) > 1:
            report.warnings.append(f"{room_id}: no exits")
        for direction, exit_meta in room.exits.items():
            if exit_dirs and direction not in exit_dirs:
                report.errors.append(f"{room_id}: exit {direction!r} is not in world.toml")
            if exit_meta.destination == room_id:
                report.errors.append(f"{room_id} {direction}: exit leads back into the same room")
                continue
            target = report.rooms.get(exit_meta.destination)
            if target is None:
                report.errors.append(
                    f"{room_id} {direction}: destination {exit_meta.destination!r} does not exist"
                )
                continue
            if target.zone != room.zone:
                report.info.append(
                    f"{room_id} {direction}: leads to zone {target.zone} ({target.id})"
                )
            back = target.exits.get(OPPOSITE.get(direction, ""))
            leads_back = back is not None and back.destination == room_id
            if exit_meta.one_way:
                report.info.append(f"{room_id} {direction} -> {target.id}: one-way")
            elif not leads_back:
                report.warnings.append(
                    f"{room_id} {direction} -> {target.id}, which does not lead back"
                )
            if abs(room.depth - target.depth) >= 2:
                report.info.append(
                    f"{room_id} -> {target.id}: depth jumps {room.depth} -> {target.depth}"
                )
        for feature in room.features:
            if not feature.description.strip():
                report.warnings.append(f"{room_id}: feature {feature.id!r} has no description")
        for spawn in room.entity_spawns:
            if spawn.template not in entities:
                report.errors.append(f"{room_id}: spawns unknown entity {spawn.template!r}")

    spawned = {s.template for r in checked.values() for s in r.entity_spawns}
    for entity in entities.values():
        if zone is not None and entity.id not in spawned:
            continue
        for row in entity.loot:
            if row.template not in items:
                report.errors.append(
                    f"entity {entity.id}: loot names unknown item {row.template!r}"
                )

    zones = sorted({r.zone for r in checked.values()})
    for zone_id in zones:
        _zone_shape(zone_id, {rid: r for rid, r in checked.items() if r.zone == zone_id}, report)
    return report


def _zone_shape(zone_id: str, rooms: dict[str, RoomModel], report: LintReport) -> None:
    """Connectivity, dead ends and feature density inside one zone."""
    if len(rooms) < 2:
        return
    neighbours: dict[str, set[str]] = {rid: set() for rid in rooms}
    for rid, room in rooms.items():
        for exit_meta in room.exits.values():
            if exit_meta.destination in rooms and exit_meta.destination != rid:
                neighbours[rid].add(exit_meta.destination)
                neighbours[exit_meta.destination].add(rid)
    start = next(iter(sorted(rooms)))
    seen, stack = {start}, [start]
    while stack:
        for nxt in neighbours[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    for rid in sorted(rooms):
        if rid not in seen:
            report.warnings.append(f"{rid}: cut off from the rest of zone {zone_id}")
        elif len(neighbours[rid]) == 1:
            report.info.append(f"{rid}: dead end")

    draws = 0
    for room in rooms.values():
        extra = room.model_extra or {}
        draws += len(room.features) + len(room.entity_spawns) + len(extra.get("hazards") or [])
        ambient = extra.get("ambient")
        draws += 1 if isinstance(ambient, dict) and ambient.get("lines") else 0
    density = draws / len(rooms)
    line = f"zone {zone_id}: feature density {density:.2f} ({draws} draws / {len(rooms)} rooms)"
    if density < DENSITY_TARGET:
        report.warnings.append(f"{line}; aim for {DENSITY_TARGET} or more")
    else:
        report.info.append(line)


def lint_world(world: Any, zone: str | None = None) -> LintReport:
    """lint_content for a world package: its declared room types and exit directions, and its
    start and respawn rooms."""
    content = world.manifest.content
    return lint_content(
        Path(world.content_dir) / "world",
        room_types=content.room_types,
        exit_dirs=content.exit_dirs,
        required_rooms=(world.start_room, world.respawn_room),
        zone=zone,
    )


def lint_room_candidate(world: Any, room_id: str, text: str) -> list[str]:
    """Errors a room file would add to its world, checked on a copy before anything is written.

    Only findings about the candidate room itself are returned, so problems elsewhere in the
    world never block a good room. The live content directory is not touched.
    """
    import shutil
    import tempfile

    zone_id, slug = room_id.split(":", 1)
    source = Path(world.content_dir) / "world"
    with tempfile.TemporaryDirectory(prefix="sage-lint-") as tmp:
        copy = Path(tmp) / "world"
        shutil.copytree(source, copy, ignore=shutil.ignore_patterns("stamps", ".positions.json"))
        target = copy / "zones" / zone_id / "rooms" / f"{slug}.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        content = world.manifest.content
        report = lint_content(
            copy, room_types=content.room_types, exit_dirs=content.exit_dirs, zone=zone_id
        )
    mine = (f"{room_id}:", f"{room_id} ", f"{zone_id}/{slug}.yaml:")
    return [e for e in report.errors if e.startswith(mine)]
