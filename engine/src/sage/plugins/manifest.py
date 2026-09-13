"""plugin.toml: identity, compatibility, dependencies and the declared ``touches`` block."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
ENTRY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$")

# Registration kinds this engine version supports. Declaring anything else in [touches] is
# accepted by the schema (forward compatible) but refused at boot if the plugin uses it.
SUPPORTED_TOUCHES = (
    "commands",
    "events_publish",
    "events_subscribe",
    "resolvers_define",
    "resolvers",
    "tick_jobs",
    "state_blocks",
    "services",
    "content_extensions",
    "routes",
    "redis_prefixes",
    "tables",
    "lexicon_prefix",
)

# Redis key prefixes the engine uses; plugins may not declare them.
ENGINE_REDIS_PREFIXES = frozenset(
    {"player", "room", "combat", "entity", "item", "heat", "wallet_pending", "session"}
)
REDIS_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class PluginError(RuntimeError):
    """A plugin cannot be loaded: bad manifest, missing dependency, or undeclared behaviour."""


def _check_spec(value: str) -> str:
    try:
        SpecifierSet(value)
    except InvalidSpecifier as exc:
        raise ValueError(f"{value!r} is not a version specifier") from exc
    return value


def caret(value: str) -> str:
    """npm-style "^1" / "^1.2" -> ">=1,<2" (world.toml [plugins] uses carets for brevity)."""
    if not value.startswith("^"):
        return value
    parts = value[1:].split(".")
    major = int(parts[0])
    lower = ".".join(parts + ["0"] * (3 - len(parts)))
    return f">={lower},<{major + 1}"


class PluginInfo(BaseModel):
    id: str
    name: str = ""
    version: str
    engine: str
    entry: str
    first_party: bool = False

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not PLUGIN_ID_RE.match(value):
            raise ValueError(f"plugin id {value!r} must match {PLUGIN_ID_RE.pattern}")
        return value

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        Version(value)
        return value

    @field_validator("engine")
    @classmethod
    def _engine(cls, value: str) -> str:
        return _check_spec(value)

    @field_validator("entry")
    @classmethod
    def _entry(cls, value: str) -> str:
        if not ENTRY_RE.match(value):
            raise ValueError(f"entry {value!r} must look like 'package.module:setup'")
        return value


class Dependency(BaseModel):
    version: str = ">=0"
    optional: bool = False

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        return _check_spec(caret(value))


class Touches(BaseModel):
    commands: list[str] = Field(default_factory=list)
    events_publish: list[str] = Field(default_factory=list)
    events_subscribe: list[str] = Field(default_factory=list)
    resolvers_define: list[str] = Field(default_factory=list)
    resolvers: list[str] = Field(default_factory=list)
    tick_jobs: list[str] = Field(default_factory=list)
    state_blocks: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    lexicon_prefix: str | None = None
    # "<kind>.<field>", e.g. "room.shop" (sage.world.extensions).
    content_extensions: list[str] = Field(default_factory=list)
    # Declared for later engine versions (contracts C.2); refused if a plugin uses them now.
    content_types: list[str] = Field(default_factory=list)
    snapshot: list[str] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    redis_prefixes: list[str] = Field(default_factory=list)
    params: list[str] = Field(default_factory=list)
    ai_slots: list[str] = Field(default_factory=list)


class PluginManifest(BaseModel):
    plugin: PluginInfo
    depends: dict[str, Dependency] = Field(default_factory=dict)
    touches: Touches = Field(default_factory=Touches)

    @model_validator(mode="before")
    @classmethod
    def _dependency_shorthand(cls, data: Any) -> Any:
        # [depends] other = "^1"  is shorthand for  other = { version = "^1" }
        deps = (data or {}).get("depends") or {}
        data["depends"] = {
            k: ({"version": v} if isinstance(v, str) else v) for k, v in deps.items()
        }
        return data

    @model_validator(mode="after")
    def _routes(self) -> PluginManifest:
        allowed = f"/plugins/{self.plugin.id}/*"
        for route in self.touches.routes:
            if route != allowed:
                raise ValueError(f"routes may only declare {allowed!r} (got {route!r})")
        return self

    @model_validator(mode="after")
    def _tables(self) -> PluginManifest:
        prefix = f"plg_{self.plugin.id}_"
        for table in self.touches.tables:
            if not table.startswith(prefix):
                raise ValueError(f"table {table!r} must be named {prefix}*")
        return self

    @model_validator(mode="after")
    def _redis_prefixes(self) -> PluginManifest:
        for prefix in self.touches.redis_prefixes:
            if not REDIS_PREFIX_RE.match(prefix):
                raise ValueError(f"redis prefix {prefix!r} must match {REDIS_PREFIX_RE.pattern}")
            if prefix in ENGINE_REDIS_PREFIXES:
                raise ValueError(f"redis prefix {prefix!r} is reserved for the engine")
        return self

    @model_validator(mode="after")
    def _lexicon_prefix(self) -> PluginManifest:
        prefix = self.touches.lexicon_prefix
        if prefix is not None and prefix != f"{self.plugin.id}.":
            raise ValueError(f"lexicon_prefix must be '{self.plugin.id}.' (got {prefix!r})")
        return self


def read_manifest(plugin_dir: Path) -> PluginManifest:
    path = Path(plugin_dir) / "plugin.toml"
    if not path.is_file():
        raise PluginError(f"no plugin.toml in {plugin_dir}")
    try:
        manifest = PluginManifest(**tomllib.loads(path.read_text(encoding="utf-8")))
    except (ValidationError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise PluginError(f"{path} is invalid: {exc}") from exc
    if manifest.plugin.id != Path(plugin_dir).name:
        raise PluginError(
            f"plugin id {manifest.plugin.id!r} must match its directory {Path(plugin_dir).name!r}"
        )
    return manifest
