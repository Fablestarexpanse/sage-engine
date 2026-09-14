"""Lexicon: every player-facing string is a key resolved through layered sources.

Resolution order (docs/sage/PHASE1_CONTRACTS.md B.5): live overrides, the world package's
``lexicon/<locale>.yaml``, plugin defaults, the engine defaults in ``sage/lexicon/en.yaml``,
and finally the literal ``[key]`` so a missing string is visible instead of silent.

Templates use ``{name}`` placeholders. A missing variable renders as ``{name}`` rather than
raising, so a bad template can never crash a command.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ENGINE_DEFAULTS = Path(__file__).with_name("en.yaml")


class _KeepMissing(dict):
    def __missing__(self, name: str) -> str:
        return "{" + name + "}"


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    """Nested YAML mappings become dotted keys: {"move": {"blocked": ...}} -> "move.blocked"."""
    out: dict[str, str] = {}
    for key, value in (data or {}).items():
        dotted = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out.update(flatten(value, dotted + "."))
        elif value is not None:
            out[dotted] = str(value)
    return out


def load_layer(path: Path) -> dict[str, str]:
    """A flattened lexicon file, or an empty layer when the file does not exist."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        return flatten(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except yaml.YAMLError:
        logger.exception("Lexicon file %s is not valid YAML; ignoring it", path)
        return {}


class Lexicon:
    """Ordered layers, highest priority first."""

    def __init__(self, layers: Iterable[tuple[str, Mapping[str, str]]]):
        self.layers = [(name, dict(values)) for name, values in layers]

    def get(self, key: str) -> str | None:
        for _, values in self.layers:
            if key in values:
                return values[key]
        return None

    def source(self, key: str) -> str | None:
        for name, values in self.layers:
            if key in values:
                return name
        return None

    def t(self, key: str, **variables: Any) -> str:
        template = self.get(key)
        if template is None:
            return f"[{key}]"
        try:
            return template.format_map(_KeepMissing(variables))
        except (ValueError, IndexError, AttributeError):
            logger.warning("Lexicon template %r is malformed: %r", key, template)
            return template

    def keys(self) -> set[str]:
        return {key for _, values in self.layers for key in values}


def build_lexicon(
    world_lexicon_dir: Path | None,
    locale: str = "en",
    *,
    overrides: Mapping[str, str] | None = None,
    plugin_layers: Iterable[tuple[str, Mapping[str, str]]] = (),
) -> Lexicon:
    layers: list[tuple[str, Mapping[str, str]]] = []
    if overrides:
        layers.append(("override", overrides))
    if world_lexicon_dir is not None:
        layers.append(("world", load_layer(Path(world_lexicon_dir) / f"{locale}.yaml")))
    layers.extend(plugin_layers)
    layers.append(("engine", load_layer(ENGINE_DEFAULTS)))
    return Lexicon(layers)


_active = build_lexicon(None)


def set_active(lexicon: Lexicon) -> None:
    """Install the lexicon the running server resolves player text through."""
    global _active
    _active = lexicon


def active() -> Lexicon:
    return _active


def t(key: str, **variables: Any) -> str:
    return _active.t(key, **variables)
