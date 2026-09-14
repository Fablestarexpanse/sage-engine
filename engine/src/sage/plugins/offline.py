"""A plugin host for tools: load a world's plugins to read what they register, then unload.

Setup runs with no database, Redis, HTTP app or sessions, so only registrations are meaningful
(content extensions, commands, panels, AI slots, resolvers). Nothing ticks and nothing is served.
Used by `python -m sage schema export`.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any


@contextlib.contextmanager
def registration_host(world: Any, root: Path) -> Iterator[Any]:
    from sage.commands.registry import CommandRegistry
    from sage.core.events import EventBus
    from sage.core.resolvers import Resolvers
    from sage.core.tick import TickManager
    from sage.llm.prompts import PromptManager
    from sage.network.panels import PanelRegistry
    from sage.network.snapshot import SnapshotContributors
    from sage.plugins import PluginHost
    from sage.world.slots import define_engine_slots

    before = set(sys.modules)
    host = PluginHost(
        world=world,
        registry=CommandRegistry(),
        events=EventBus(),
        resolvers=Resolvers(),
        tick_manager=TickManager(),
        redis=None,
        plugins_root=root / "plugins",
        trusted_roots=[root / "plugins", root / "worlds"],
    )
    define_engine_slots(host.resolvers, world)
    host.server = SimpleNamespace(
        snapshot_contributors=SnapshotContributors(),
        panels=PanelRegistry(),
        prompt_manager=PromptManager(world.prompts_dir, world.style_path),
        persistence=SimpleNamespace(flush_hooks=[]),
    )
    host.load()
    try:
        yield host
    finally:
        host.teardown()
        # Plugin modules imported here must not leak into a later host for another world.
        for name in set(sys.modules) - before:
            if name.startswith(("sage_plugins", "sage_worlds")):
                del sys.modules[name]
