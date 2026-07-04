"""HotReloader — watches content/ and commands/ for changes and triggers cache invalidation."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class ReloadHandler(FileSystemEventHandler):
    """Handles file system events and triggers debounced callbacks."""

    def __init__(self, callback: Callable[[Path], Any], loop: asyncio.AbstractEventLoop):
        self.callback = callback
        self.loop = loop
        self._pending_reloads: dict[Path, asyncio.TimerHandle] = {}
        self.debounce_delay = 0.5  # seconds

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith((".yaml", ".py", ".j2")):
            path = Path(event.src_path)
            self._debounce_reload(path)

    def _debounce_reload(self, path: Path):
        """Prevents multiple reloads for the same file in rapid succession."""
        if path in self._pending_reloads:
            self._pending_reloads[path].cancel()

        # Schedule the reload on the main event loop
        handle = self.loop.call_later(
            self.debounce_delay,
            lambda: asyncio.run_coroutine_threadsafe(self.callback(path), self.loop),
        )
        self._pending_reloads[path] = handle


class HotReloader:
    """
    Service that watches the project directory for changes
    and notifies the engine to reload specific components.
    """

    def __init__(self, reload_callback: Callable[[Path], Any]):
        self.reload_callback = reload_callback
        self.observer = Observer()
        self.is_running = False

    async def start(self, watch_paths: list[str]):
        """Start the watchdog observer."""
        loop = asyncio.get_running_loop()
        handler = ReloadHandler(self.reload_callback, loop)

        for p in watch_paths:
            path = Path(p)
            if path.exists():
                self.observer.schedule(handler, str(path), recursive=True)
                logger.info(f"Hot-reload watching: {path}")

        self.observer.start()
        self.is_running = True

    def stop(self):
        """Stop the watchdog observer."""
        if self.is_running:
            self.observer.stop()
            self.observer.join()
            self.is_running = False
            logger.info("Hot-reload stopped.")
