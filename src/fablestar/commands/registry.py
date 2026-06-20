"""CommandRegistry and @command decorator — registers handlers at import time."""

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

    def reload_module(self, module_name: str):
        """Hot-reload commands from a specific module."""
        try:
            if module_name in self._modules:
                module = importlib.reload(self._modules[module_name])
            else:
                module = importlib.import_module(module_name)
                self._modules[module_name] = module

            # Re-scaning module for registration is one way,
            # but we'll use the decorator pattern which triggers on import/reload.
            logger.info(f"Reloaded command module: {module_name}")
        except Exception as e:
            logger.error(f"Failed to reload command module {module_name}: {e}")


# Global registry instance
registry = CommandRegistry()


def command(name: str, aliases: list[str] | None = None):
    """Decorator to register a function as a command."""

    def decorator(func):
        registry.register(name, func, aliases)
        return func

    return decorator
