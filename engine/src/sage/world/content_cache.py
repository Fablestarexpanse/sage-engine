"""Hot-reloadable view of one content directory for plugins.

A plugin that reads YAML from ``<content_dir>/<subdir>/`` wraps its loader in :class:`DirCache`;
``get()`` reloads only when a file in that directory was added, removed or changed, so content
edits apply without a restart and without a plugin-specific hook into the engine's hot reloader.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")


class DirCache(Generic[T]):
    def __init__(self, directory: Path, loader: Callable[[Path], T], pattern: str = "*.yaml"):
        self._dir = Path(directory)
        self._loader = loader
        self._pattern = pattern
        self._stamp: tuple | None = None
        self._value: T | None = None

    @property
    def directory(self) -> Path:
        return self._dir

    def get(self) -> T:
        files = sorted(self._dir.glob(self._pattern)) if self._dir.is_dir() else []
        stamp = tuple((f.name, f.stat().st_mtime_ns) for f in files)
        if stamp != self._stamp or self._value is None:
            self._value = self._loader(self._dir)
            self._stamp = stamp
        return self._value
