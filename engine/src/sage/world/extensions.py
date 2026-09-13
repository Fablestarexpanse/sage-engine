"""Content schema extensions (contracts catalog #7): plugin-owned fields on engine content models.

Rooms, room features, item templates and entity templates accept fields the engine does not
define. A plugin claims one with ``api.content.extend("room", "shop", ShopModel)``; it then reads a validated
``ShopModel`` for a room with ``api.content.extension(room, "room", "shop")``. A block that fails
validation is logged once (with the content id) and reads as absent, so one bad YAML block
cannot take a room down. Fields nobody claims are kept on the model (and so survive editor
round-trips) but mean nothing to the running game.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from sage.world.models import EntityTemplate, FeatureModel, ItemTemplate, RoomModel

logger = logging.getLogger(__name__)

KINDS: dict[str, type[BaseModel]] = {
    "room": RoomModel,
    "item": ItemTemplate,
    "entity": EntityTemplate,
    "feature": FeatureModel,
}

_INVALID = object()
# Validated values are cached per content object; loaders replace objects on reload, and the
# cache is dropped wholesale once it grows past this many objects.
_CACHE_LIMIT = 4096


class ExtensionError(ValueError):
    pass


class ContentExtensions:
    def __init__(self) -> None:
        self._fields: dict[tuple[str, str], tuple[str, type[BaseModel]]] = {}
        self._cache: dict[int, tuple[Any, dict[str, Any]]] = {}

    def register(self, kind: str, name: str, model: type[BaseModel], owner: str) -> None:
        if kind not in KINDS:
            raise ExtensionError(f"unknown content kind {kind!r} (expected one of {sorted(KINDS)})")
        if name in KINDS[kind].model_fields:
            raise ExtensionError(f"{kind}.{name} is an engine field and cannot be extended")
        claimed = self._fields.get((kind, name))
        if claimed is not None and claimed[0] != owner:
            raise ExtensionError(f"{kind}.{name} is already claimed by {claimed[0]}")
        self._fields[(kind, name)] = (owner, model)
        self._cache.clear()

    def withdraw(self, owner: str) -> None:
        self._fields = {key: v for key, v in self._fields.items() if v[0] != owner}
        self._cache.clear()

    def owner(self, kind: str, name: str) -> str | None:
        claimed = self._fields.get((kind, name))
        return claimed[0] if claimed else None

    def get(self, obj: Any, kind: str, name: str) -> Any:
        """The validated extension block on a content object, or None when absent or invalid."""
        claimed = self._fields.get((kind, name))
        if claimed is None or obj is None:
            return None
        entry = self._cache.get(id(obj))
        if entry is None or entry[0] is not obj:
            if len(self._cache) >= _CACHE_LIMIT:
                self._cache.clear()
            entry = (obj, {})
            self._cache[id(obj)] = entry
        values = entry[1]
        if name not in values:
            raw = (getattr(obj, "model_extra", None) or {}).get(name)
            if raw is None:
                values[name] = None
            else:
                try:
                    values[name] = claimed[1].model_validate(raw)
                except ValidationError as exc:
                    logger.error(
                        "%s %s: invalid %r block (owned by %s): %s",
                        kind,
                        getattr(obj, "id", "?"),
                        name,
                        claimed[0],
                        exc,
                    )
                    values[name] = _INVALID
        value = values[name]
        return None if value is _INVALID else value

    def schemas(self) -> dict[str, dict[str, Any]]:
        """JSON Schema per claimed field, keyed "<kind>.<field>" (for editors and validation)."""
        return {
            f"{kind}.{name}": {"owner": owner, "schema": model.model_json_schema()}
            for (kind, name), (owner, model) in sorted(self._fields.items())
        }
