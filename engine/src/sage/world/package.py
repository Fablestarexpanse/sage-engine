"""World packages: load, validate and select the world a deployment runs.

A world package is a directory under ``worlds/<id>/`` (docs/sage/PHASE1_CONTRACTS.md Part B)
with a ``world.toml`` manifest, a stat schema (``stats.yaml``) and in-world currencies
(``currencies.yaml``). The engine reads everything world-specific through the loaded
:class:`WorldPackage`, never from hardcoded paths or ids.

Everything a world ships lives inside its directory: ``content/``, ``lexicon/``, ``ai/`` and
``plugins/``.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from sage import ENGINE_VERSION

WORLD_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class WorldPackageError(ValueError):
    """A world package is missing, malformed, or incompatible with this engine."""


class WorldInfo(BaseModel):
    id: str
    name: str
    version: str
    engine: str
    locale: str = "en"

    @field_validator("id")
    @classmethod
    def _id_format(cls, value: str) -> str:
        if not WORLD_ID_RE.match(value):
            raise ValueError(f"world id {value!r} must match {WORLD_ID_RE.pattern}")
        return value

    @field_validator("version")
    @classmethod
    def _semver(cls, value: str) -> str:
        Version(value)
        return value

    @field_validator("engine")
    @classmethod
    def _range(cls, value: str) -> str:
        try:
            SpecifierSet(value)
        except InvalidSpecifier as exc:
            raise ValueError(f"engine range {value!r} is not a version specifier") from exc
        return value


class StartInfo(BaseModel):
    room: str
    respawn: str

    @field_validator("room", "respawn")
    @classmethod
    def _room_id(cls, value: str) -> str:
        if value.count(":") != 1 or not all(value.split(":")):
            raise ValueError(f"room id {value!r} must look like zone_id:room_slug")
        return value


class ContentInfo(BaseModel):
    room_types: list[str] = Field(default_factory=list)
    exit_dirs: list[str] = Field(default_factory=list)
    equipment_slots: list[str] = Field(default_factory=list)


class WorldManifest(BaseModel):
    world: WorldInfo
    start: StartInfo
    content: ContentInfo = Field(default_factory=ContentInfo)
    plugins: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _no_transition(cls, data: Any) -> Any:
        if isinstance(data, dict) and "transition" in data:
            raise ValueError(
                "[transition] was removed in SAGE 0.2: a world's content, prompts and assets "
                "live inside its package (content/, ai/)"
            )
        return data


class Attribute(BaseModel):
    key: str
    label: str
    short: str | None = None
    min: int
    max: int
    default: int

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not KEY_RE.match(value):
            raise ValueError(f"stat key {value!r} must match {KEY_RE.pattern}")
        return value


class Vital(BaseModel):
    key: str
    label: str
    default_max: int


class Chargen(BaseModel):
    attribute_points: int | None = None


class StatSchema(BaseModel):
    attributes: list[Attribute] = Field(default_factory=list)
    vitals: list[Vital] = Field(default_factory=list)
    chargen: Chargen = Field(default_factory=Chargen)


class Currency(BaseModel):
    key: str
    label: str
    starting: int = 0
    integer: bool = True

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not KEY_RE.match(value):
            raise ValueError(f"currency key {value!r} must match {KEY_RE.pattern}")
        return value


@dataclass(frozen=True)
class WorldPackage:
    """A validated world package and the paths the engine reads from it."""

    root: Path
    manifest: WorldManifest
    stats: StatSchema
    currencies: list[Currency] = field(default_factory=list)
    # Read content from here instead of <root>/content (tests and tools only; not in world.toml).
    content_override: Path | None = None

    @property
    def id(self) -> str:
        return self.manifest.world.id

    @property
    def start_room(self) -> str:
        return self.manifest.start.room

    @property
    def respawn_room(self) -> str:
        return self.manifest.start.respawn

    @property
    def content_dir(self) -> Path:
        return self.content_override or self.root / "content"

    def with_content_dir(self, path: Path | str) -> WorldPackage:
        """The same package reading content from another directory (tests, tools)."""
        return replace(self, content_override=Path(path))

    @property
    def prompts_dir(self) -> Path:
        return self.ai_dir / "prompts"

    def param(self, key: str, default: Any = None) -> Any:
        """A world.toml [params] value, or default when the world does not set it."""
        return self.manifest.params.get(key, default)

    @property
    def ai_dir(self) -> Path:
        return self.root / "ai"

    @property
    def style_path(self) -> Path:
        return self.ai_dir / "style.yaml"

    @property
    def lexicon_dir(self) -> Path:
        return self.root / "lexicon"

    @property
    def zones_dir(self) -> Path:
        return self.content_dir / "world" / "zones"


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise WorldPackageError(f"{path.name} is missing from {path.parent}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorldPackageError(f"{path} is not valid YAML: {exc}") from exc


def load_world_package(world_dir: Path) -> WorldPackage:
    """Load and validate one package directory."""
    world_dir = Path(world_dir)
    manifest_path = world_dir / "world.toml"
    if not manifest_path.is_file():
        raise WorldPackageError(f"no world.toml in {world_dir}")
    try:
        manifest = WorldManifest(**tomllib.loads(manifest_path.read_text(encoding="utf-8")))
        stats = StatSchema(**(_read_yaml(world_dir / "stats.yaml") or {}))
        currencies = [Currency(**c) for c in (_read_yaml(world_dir / "currencies.yaml") or [])]
    except (ValidationError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise WorldPackageError(f"world package {world_dir} is invalid: {exc}") from exc

    if manifest.world.id != world_dir.name:
        raise WorldPackageError(
            f"world id {manifest.world.id!r} must match its directory name {world_dir.name!r}"
        )
    if Version(ENGINE_VERSION) not in SpecifierSet(manifest.world.engine):
        raise WorldPackageError(
            f"world {manifest.world.id!r} needs engine {manifest.world.engine}, "
            f"this is {ENGINE_VERSION}"
        )
    package = WorldPackage(world_dir.resolve(), manifest, stats, currencies)
    if not package.content_dir.is_dir():
        raise WorldPackageError(f"content directory {package.content_dir} does not exist")
    return package


def available_worlds(worlds_dir: Path) -> list[str]:
    worlds_dir = Path(worlds_dir)
    if not worlds_dir.is_dir():
        return []
    return sorted(
        p.name for p in worlds_dir.iterdir() if (p / "world.toml").is_file() and p.name[0] != "_"
    )


def select_world(worlds_dir: Path, requested: str | None) -> WorldPackage:
    """The configured world, or the only one present. Several worlds need an explicit choice."""
    worlds = available_worlds(worlds_dir)
    if requested:
        if requested not in worlds:
            raise WorldPackageError(
                f"world {requested!r} not found in {worlds_dir} (available: {worlds or 'none'})"
            )
        return load_world_package(Path(worlds_dir) / requested)
    if len(worlds) == 1:
        return load_world_package(Path(worlds_dir) / worlds[0])
    if not worlds:
        raise WorldPackageError(f"no world packages found in {worlds_dir}")
    raise WorldPackageError(
        f"several worlds in {worlds_dir} ({', '.join(worlds)}): set server.world in "
        "config/server.toml or SAGE_SERVER__WORLD"
    )
