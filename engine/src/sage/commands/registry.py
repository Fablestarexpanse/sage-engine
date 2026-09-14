"""CommandRegistry and @command decorator — registers handlers at import time."""

import asyncio
import importlib
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class Command:
    """Represents a registered game command."""

    def __init__(self, name: str, handler: Callable, aliases: list[str] | None = None):
        self.name = name
        self.handler = handler
        self.aliases = aliases or []


class CommandRegistry:
    """
    Registry for all game commands.
    Supports dynamic registration and hot-reloading of command modules.
    """

    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}
        self._modules: dict[str, Any] = {}

    def register(self, name: str, handler: Callable, aliases: list[str] | None = None):
        """Register a command and its aliases."""
        cmd = Command(name, handler, aliases)
        self._commands[name] = cmd
        if aliases:
            for alias in aliases:
                self._aliases[alias] = name
        logger.debug(f"Registered command: {name} (aliases: {aliases})")

    def names(self) -> list[str]:
        """Every registered command's primary name, sorted (engine and plugin commands alike)."""
        return sorted(self._commands)

    def get(self, name: str) -> Command | None:
        """Retrieve a command by name or alias."""
        # Check primary name
        if name in self._commands:
            return self._commands[name]

        # Check aliases
        if name in self._aliases:
            primary_name = self._aliases[name]
            return self._commands.get(primary_name)

        return None

    def _unregister_module(self, module_name: str) -> None:
        """Remove every command (and its aliases) whose handler was defined in module_name."""
        gone = {
            name
            for name, cmd in self._commands.items()
            if getattr(cmd.handler, "__module__", None) == module_name
        }
        for name in gone:
            del self._commands[name]
        self._aliases = {a: target for a, target in self._aliases.items() if target not in gone}

    def load_module_strict(self, module_name: str):
        """Import a command module, re-raising on failure.

        Use at server boot: a broken command module must abort startup
        instead of logging an error and reporting "Startup complete".
        """
        if module_name in self._modules:
            # Drop this module's commands first so ones deleted from the source disappear;
            # restore everything if the new source fails to import.
            commands, aliases = dict(self._commands), dict(self._aliases)
            self._unregister_module(module_name)
            try:
                module = importlib.reload(self._modules[module_name])
            except BaseException:
                self._commands, self._aliases = commands, aliases
                raise
        else:
            module = importlib.import_module(module_name)
            self._modules[module_name] = module
        # Registration happens via the @command decorator on import/reload.
        logger.info(f"Loaded command module: {module_name}")

    def unregister(self, name: str) -> None:
        """Remove a command and every alias pointing at it (plugin teardown)."""
        self._commands.pop(name, None)
        self._aliases = {a: target for a, target in self._aliases.items() if target != name}

    def reload_module(self, module_name: str):
        """Hot-reload commands from a specific module (lenient: log and keep running)."""
        try:
            self.load_module_strict(module_name)
        except Exception as e:
            logger.error(f"Failed to reload command module {module_name}: {e}")


# Global registry instance
registry = CommandRegistry()


def command(name: str, aliases: list[str] | None = None):
    """Decorator to register a function as a command. Handler must be async."""

    def decorator(func):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"Command handler '{name}' must be an async function, got {func!r}")
        registry.register(name, func, aliases)
        return func

    return decorator
