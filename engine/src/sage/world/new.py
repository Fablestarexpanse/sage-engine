"""`sage world new <id>`: make a world package with one start room and no map.

The files come from the template in ``sage/templates/world``. Rooms, exits and layout are drawn
afterwards in WorldForge; this only produces a package WorldForge can open and the engine can
boot. It works offline: no database is created. It ends by validating the new package and
exporting its content schema, and refuses to leave a package that does not validate.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "world"
WORLD_ID = re.compile(r"[a-z][a-z0-9_]{1,31}")


class WorldNewError(ValueError):
    """A world the command refuses to make (bad id, existing directory, invalid result)."""


@dataclass
class NewWorld:
    path: Path
    written: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def engine_range(version: str) -> str:
    """The engine range a new package pins: this minor release line (0.2.0 -> >=0.2,<0.3)."""
    major, minor = (int(p) for p in version.split(".")[:2])
    return f">={major}.{minor},<{major}.{minor + 1}"


def plugin_lines(plugins_dir: Path) -> str:
    """One commented line per first-party plugin: `# <id> = "^<major>"  # <name>`."""
    lines = []
    for manifest in sorted(plugins_dir.glob("*/plugin.toml")):
        try:
            info = tomllib.loads(manifest.read_text(encoding="utf-8")).get("plugin", {})
        except (OSError, tomllib.TOMLDecodeError):
            continue
        plugin_id, version = info.get("id"), str(info.get("version", "1"))
        if not plugin_id:
            continue
        major = version.split(".")[0]
        lines.append(f'# {plugin_id} = "^{major}"'.ljust(28) + f"  # {info.get('name', plugin_id)}")
    return "\n".join(lines) or "# (no first-party plugins found)"


def create_world(
    world_id: str,
    worlds_dir: Path,
    project_root: Path,
    *,
    name: str | None = None,
    force: bool = False,
) -> NewWorld:
    """Write the package, validate it and export its schema. Raises WorldNewError on refusal."""
    from sage import ENGINE_VERSION

    if not WORLD_ID.fullmatch(world_id or ""):
        raise WorldNewError(
            f"world id {world_id!r}: start with a lowercase letter, then 1-31 lowercase letters, "
            "digits or underscores"
        )
    target = Path(worlds_dir) / world_id
    if target.exists() and not force:
        raise WorldNewError(f"{target} already exists (use --force to rewrite the template files)")
    title = (name or world_id.replace("_", " ").title()).strip()
    if not title or '"' in title or "\n" in title:
        raise WorldNewError("world name must be one line without double quotes")

    values = {
        "__WORLD_ID__": world_id,
        "__WORLD_NAME__": title,
        "__ENGINE_RANGE__": engine_range(ENGINE_VERSION),
        "__PLUGIN_LINES__": plugin_lines(Path(project_root) / "plugins"),
    }
    result = NewWorld(path=target)
    for source in sorted(p for p in TEMPLATE.rglob("*") if p.is_file()):
        rel = source.relative_to(TEMPLATE).as_posix()
        text = source.read_text(encoding="utf-8")
        for token, value in values.items():
            text = text.replace(token, value)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # --force rewrites the template's own files and never touches anything else.
        dest.write_text(text, encoding="utf-8", newline="\n")
        result.written.append(rel)

    _check(result, project_root)
    return result


def _check(result: NewWorld, project_root: Path) -> None:
    from sage.plugins.offline import registration_host
    from sage.world.lint import lint_world
    from sage.world.package import WorldPackageError, load_world_package
    from sage.world.schema import SCHEMA_FILE, content_schema, dumps

    try:
        world = load_world_package(result.path)
    except WorldPackageError as exc:
        result.errors.append(str(exc))
        return
    report = lint_world(world)
    result.errors += report.errors
    result.warnings += report.warnings
    with registration_host(world, Path(project_root)) as host:
        (result.path / SCHEMA_FILE).write_text(
            dumps(content_schema(world, host.extensions)), encoding="utf-8", newline="\n"
        )
    result.written.append(SCHEMA_FILE)
