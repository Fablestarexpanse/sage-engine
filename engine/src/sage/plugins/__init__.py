"""SAGE plugin system: host that loads a world's enabled plugins (contracts Part C)."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sage.plugins.api import PluginAPI
from sage.plugins.loader import (
    PluginRecord,
    discover,
    import_entry,
    load_lexicon_layer,
    seal,
    trust_banner,
)
from sage.plugins.manifest import PluginError
from sage.world.extensions import ContentExtensions

logger = logging.getLogger(__name__)

__all__ = ["PluginError", "PluginHost"]


@dataclass
class PluginHost:
    """Everything a plugin may register against, plus the plugins loaded into it."""

    world: Any
    registry: Any
    events: Any
    resolvers: Any
    tick_manager: Any
    redis: Any
    plugins_root: Path
    trusted_roots: list[Path]
    content: Any = None  # ContentLoader
    http: Any = None  # the Nexus FastAPI app (None in hosts without HTTP)
    server: Any = None  # the running server: sessions, spawner (None in bare hosts)
    extensions: ContentExtensions = field(default_factory=ContentExtensions)
    services: dict[str, tuple[str, Any]] = field(default_factory=dict)
    state_owners: dict[str, str] = field(default_factory=dict)
    # (owner, () -> names) — character names players may not take.
    name_claims: list[tuple[str, Any]] = field(default_factory=list)
    loaded: list[PluginRecord] = field(default_factory=list)

    def discover(self) -> list[PluginRecord]:
        """Validated, dependency-ordered records for the world's enabled plugins (no imports)."""
        return discover(self.world, self.plugins_root, self.trusted_roots)

    def load(self, records: list[PluginRecord] | None = None) -> list[PluginRecord]:
        for record in records if records is not None else self.discover():
            trust_banner(record)
            record.lexicon = load_lexicon_layer(record)
            api = PluginAPI(self, record)
            record.api = api
            try:
                setup = import_entry(record)
                result = setup(api)
                if inspect.isawaitable(result):
                    raise PluginError(f"plugin {record.id}: setup(api) must be synchronous")
                seal(record)
            except Exception:
                api.withdraw()
                self.teardown()
                raise
            module = inspect.getmodule(setup)
            record.teardown = getattr(module, "teardown", None)
            self.loaded.append(record)
            logger.info(
                "Plugin %s %s loaded from %s",
                record.id,
                record.manifest.plugin.version,
                record.path,
            )
        return self.loaded

    def lexicon_layers(self) -> list[tuple[str, dict[str, str]]]:
        # Later-loaded plugins sit above earlier ones (a dependent can reword its dependency).
        return [(f"plugin:{r.id}", r.lexicon) for r in reversed(self.loaded) if r.lexicon]

    def teardown(self) -> None:
        for record in reversed(self.loaded):
            if record.teardown is not None:
                try:
                    record.teardown(record.api)
                except Exception:
                    logger.exception("Plugin %s teardown failed", record.id)
            record.api.withdraw()
        self.loaded.clear()
