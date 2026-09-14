"""Static checks of a world package's content, for tests and tools (no server, no database).

Errors are things that break play: a room that fails its schema or has the wrong id, an exit to a
room that does not exist, a spawn or loot row naming a missing template, a start or respawn room
that is not there, and room types or exit directions the world's `world.toml` does not declare
(when it declares any). Warnings are map smells: a two-way exit whose far side does not lead back.
"""

from __future__ import annotations

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


@dataclass
class LintReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rooms: dict[str, RoomModel] = field(default_factory=dict)


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _templates(directory: Path, model: type, report: LintReport) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in sorted(directory.glob("*.yaml")) if directory.is_dir() else []:
        try:
            doc = model(**_load(path))
        except (ValidationError, TypeError, yaml.YAMLError) as exc:
            report.errors.append(f"{path.name}: {exc}".splitlines()[0])
            continue
        out[doc.id] = doc
    return out


def lint_world(world: Any) -> LintReport:
    report = LintReport()
    base = Path(world.content_dir) / "world"
    content = world.manifest.content
    room_types = set(content.room_types)
    exit_dirs = set(content.exit_dirs)

    for path in sorted((base / "zones").glob("*/rooms/*.yaml")):
        zone = path.parent.parent.name
        try:
            room = RoomModel(**_load(path))
        except (ValidationError, TypeError, yaml.YAMLError) as exc:
            report.errors.append(f"{zone}/{path.name}: {exc}".splitlines()[0])
            continue
        if room.id != f"{zone}:{path.stem}":
            report.errors.append(f"{path}: id {room.id!r} should be {zone}:{path.stem}")
        report.rooms[room.id] = room

    entities = _templates(base / "entities", EntityTemplate, report)
    items = _templates(base / "items", ItemTemplate, report)

    for room_id in (world.start_room, world.respawn_room):
        if room_id not in report.rooms:
            report.errors.append(f"world.toml names room {room_id!r}, which does not exist")

    for room_id, room in sorted(report.rooms.items()):
        if room_types and room.type not in room_types:
            report.errors.append(f"{room_id}: room type {room.type!r} is not in world.toml")
        for direction, exit_meta in room.exits.items():
            if exit_dirs and direction not in exit_dirs:
                report.errors.append(f"{room_id}: exit {direction!r} is not in world.toml")
            target = report.rooms.get(exit_meta.destination)
            if target is None:
                report.errors.append(
                    f"{room_id} {direction}: destination {exit_meta.destination!r} does not exist"
                )
                continue
            back = target.exits.get(OPPOSITE.get(direction, ""))
            if not exit_meta.one_way and (back is None or back.destination != room_id):
                report.warnings.append(
                    f"{room_id} {direction} -> {target.id}, which does not lead back"
                )
        for spawn in room.entity_spawns:
            if spawn.template not in entities:
                report.errors.append(f"{room_id}: spawns unknown entity {spawn.template!r}")

    for entity in entities.values():
        for row in entity.loot:
            if row.template not in items:
                report.errors.append(
                    f"entity {entity.id}: loot names unknown item {row.template!r}"
                )
    return report
