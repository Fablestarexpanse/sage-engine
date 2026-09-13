"""Plugin discovery, ordering, loading and sealing (docs/sage/PHASE1_CONTRACTS.md Part C).

Lifecycle: discover the world's enabled plugins -> validate manifests and version ranges ->
order by dependencies -> warn about untrusted code -> import and call ``setup(api)`` ->
seal (anything registered but not declared in ``[touches]`` fails boot) -> started.
Plugins are imported by path under ``sage_plugins.<id>`` (first-party, ``plugins/``) or
``sage_worlds.<world>.plugins.<id>`` (world-private), never from the engine's import path.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from sage import ENGINE_VERSION
from sage.lexicon import load_layer
from sage.plugins.manifest import (
    SUPPORTED_TOUCHES,
    PluginError,
    PluginManifest,
    caret,
    read_manifest,
)

logger = logging.getLogger(__name__)


@dataclass
class PluginRecord:
    manifest: PluginManifest
    path: Path
    module_base: str
    trusted: bool
    registered: dict[str, set[str]] = field(default_factory=dict)
    lexicon: dict[str, str] = field(default_factory=dict)
    teardown: Callable[[Any], Any] | None = None
    api: Any = None

    @property
    def id(self) -> str:
        return self.manifest.plugin.id

    def record(self, kind: str, name: str) -> None:
        self.registered.setdefault(kind, set()).add(name)


def _locate(plugin_id: str, world: Any, plugins_root: Path) -> tuple[Path, str]:
    world_private = world.root / "plugins" / plugin_id
    first_party = plugins_root / plugin_id
    if (world_private / "plugin.toml").is_file():
        if (first_party / "plugin.toml").is_file():
            logger.info("Plugin %s: world-private copy shadows plugins/%s", plugin_id, plugin_id)
        return world_private, f"sage_worlds.{world.id}.plugins.{plugin_id}"
    if (first_party / "plugin.toml").is_file():
        return first_party, f"sage_plugins.{plugin_id}"
    raise PluginError(
        f"world {world.id!r} enables plugin {plugin_id!r} but it is in neither "
        f"{world_private} nor {first_party}"
    )


def _is_within(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(root.resolve()) for root in roots)


def discover(world: Any, plugins_root: Path, trusted_roots: list[Path]) -> list[PluginRecord]:
    records: dict[str, PluginRecord] = {}
    for plugin_id, wanted in sorted(world.manifest.plugins.items()):
        path, module_base = _locate(plugin_id, world, plugins_root)
        manifest = read_manifest(path)
        info = manifest.plugin
        if Version(ENGINE_VERSION) not in SpecifierSet(info.engine):
            raise PluginError(
                f"plugin {plugin_id} needs engine {info.engine}, this is {ENGINE_VERSION}"
            )
        if Version(info.version) not in SpecifierSet(caret(wanted)):
            raise PluginError(
                f"world {world.id!r} wants plugin {plugin_id} {wanted}, found {info.version}"
            )
        trusted = info.first_party and _is_within(path, trusted_roots)
        records[plugin_id] = PluginRecord(manifest, path, module_base, trusted)

    for record in records.values():
        for dep_id, dep in record.manifest.depends.items():
            target = records.get(dep_id)
            if target is None:
                if dep.optional:
                    continue
                raise PluginError(
                    f"plugin {record.id} requires {dep_id} ({dep.version}), which world "
                    f"{world.id!r} does not enable"
                )
            if Version(target.manifest.plugin.version) not in SpecifierSet(dep.version):
                raise PluginError(
                    f"plugin {record.id} requires {dep_id} {dep.version}, "
                    f"found {target.manifest.plugin.version}"
                )
    return order(records)


def order(records: dict[str, PluginRecord]) -> list[PluginRecord]:
    """Dependencies first; ties broken by id so load order is deterministic."""
    edges = {pid: {d for d in rec.manifest.depends if d in records} for pid, rec in records.items()}
    ordered: list[PluginRecord] = []
    ready = sorted(pid for pid, deps in edges.items() if not deps)
    while ready:
        pid = ready.pop(0)
        ordered.append(records[pid])
        for other, deps in edges.items():
            if pid in deps:
                deps.discard(pid)
                if not deps and records[other] not in ordered and other not in ready:
                    ready.append(other)
                    ready.sort()
    if len(ordered) != len(records):
        stuck = sorted(pid for pid in records if records[pid] not in ordered)
        raise PluginError(f"plugin dependency cycle among: {', '.join(stuck)}")
    return ordered


def _ensure_namespace(name: str) -> None:
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        prefix = ".".join(parts[:i])
        if prefix not in sys.modules:
            module = types.ModuleType(prefix)
            module.__path__ = []  # namespace-like parent
            sys.modules[prefix] = module


def import_entry(record: PluginRecord) -> Callable[[Any], Any]:
    module_path, func_name = record.manifest.plugin.entry.split(":")
    package, _, rest = module_path.partition(".")
    package_dir = record.path / package
    init = package_dir / "__init__.py"
    if not init.is_file():
        raise PluginError(f"plugin {record.id}: entry package {package_dir} has no __init__.py")
    _ensure_namespace(record.module_base)
    full_package = f"{record.module_base}.{package}"
    if full_package not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            full_package, init, submodule_search_locations=[str(package_dir)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_package] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(full_package, None)
            raise
    module = importlib.import_module(f"{full_package}.{rest}" if rest else full_package)
    setup = getattr(module, func_name, None)
    if not callable(setup):
        raise PluginError(f"plugin {record.id}: {record.manifest.plugin.entry} is not callable")
    return setup


def seal(record: PluginRecord) -> None:
    """Fail on registrations the manifest did not declare; warn about unused declarations."""
    touches = record.manifest.touches
    for kind, names in record.registered.items():
        if kind not in SUPPORTED_TOUCHES:
            raise PluginError(f"plugin {record.id} used unsupported registration kind {kind!r}")
        declared = set(getattr(touches, kind))
        undeclared = sorted(names - declared)
        if undeclared:
            raise PluginError(
                f"plugin {record.id} registered {kind} {undeclared} not declared in "
                f"[touches].{kind} of {record.path / 'plugin.toml'}"
            )
    for kind in SUPPORTED_TOUCHES:
        if kind == "lexicon_prefix":
            continue
        unused = sorted(set(getattr(touches, kind)) - record.registered.get(kind, set()))
        if unused and kind not in ("events_publish", "redis_prefixes"):
            logger.warning(
                "Plugin %s declares %s %s but never registered them", record.id, kind, unused
            )
    for kind, value in touches.model_dump().items():
        if kind not in SUPPORTED_TOUCHES and value:
            logger.warning(
                "Plugin %s declares %s, which this engine version (%s) does not support yet",
                record.id,
                kind,
                ENGINE_VERSION,
            )


def trust_banner(record: PluginRecord) -> None:
    if record.trusted:
        return
    logger.warning(
        "\n%s\nLOADING NON-FIRST-PARTY PLUGIN %s %s\n  path: %s\n  touches: %s\n"
        "SAGE does not sandbox plugins; this code runs with full engine access.\n%s",
        "!" * 72,
        record.id,
        record.manifest.plugin.version,
        record.path,
        {k: v for k, v in record.manifest.touches.model_dump().items() if v},
        "!" * 72,
    )


def load_lexicon_layer(record: PluginRecord) -> dict[str, str]:
    layer = load_layer(record.path / "lexicon" / "en.yaml")
    prefix = record.manifest.touches.lexicon_prefix
    if layer and prefix is None:
        raise PluginError(
            f"plugin {record.id} ships lexicon strings but declares no lexicon_prefix"
        )
    outside = sorted(k for k in layer if prefix and not k.startswith(prefix))
    if outside:
        raise PluginError(f"plugin {record.id} lexicon keys outside {prefix!r}: {outside}")
    return layer
