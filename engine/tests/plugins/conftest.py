"""Helpers for testing first-party and world plugins through the real plugin host."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sage import lexicon
from sage.commands.registry import CommandRegistry
from sage.core.events import EventBus
from sage.core.resolvers import Resolvers
from sage.core.tick import TickManager
from sage.plugins import PluginHost
from sage.world.loader import ContentLoader
from sage.world.slots import define_engine_slots
from tests.fakes import FakeRedis

REPO_ROOT = Path(__file__).resolve().parents[3]

# First-party plugin packages are importable directly so their pure rules can be unit-tested.
# Behaviour through the engine is tested via plugin_host, which loads them the way servers do.
for _plugin_dir in sorted((REPO_ROOT / "plugins").iterdir()):
    if (_plugin_dir / "plugin.toml").is_file() and str(_plugin_dir) not in sys.path:
        sys.path.insert(0, str(_plugin_dir))


@pytest.fixture
def plugin_host():
    """plugin_host(world, ids=None, server=None) -> PluginHost with plugins loaded, lexicon active."""
    hosts: list[PluginHost] = []
    previous = lexicon.active()

    def build(world, plugin_ids: list[str] | None = None, server=None) -> PluginHost:
        if plugin_ids is not None:
            manifest = world.manifest.model_copy(deep=True)
            manifest.plugins = {pid: world.manifest.plugins.get(pid, ">=0") for pid in plugin_ids}
            world = type(world)(world.root, manifest, world.stats, world.currencies)
        host = PluginHost(
            world=world,
            registry=CommandRegistry(),
            events=EventBus(),
            resolvers=Resolvers(),
            tick_manager=TickManager(),
            redis=FakeRedis(),
            content=ContentLoader(world.content_dir),
            plugins_root=REPO_ROOT / "plugins",
            trusted_roots=[REPO_ROOT / "plugins", REPO_ROOT / "worlds"],
        )
        define_engine_slots(host.resolvers)
        host.server = server
        host.load()
        lexicon.set_active(
            lexicon.build_lexicon(world.lexicon_dir, plugin_layers=host.lexicon_layers())
        )
        hosts.append(host)
        return host

    yield build
    lexicon.set_active(previous)
    for host in hosts:
        host.teardown()
    for name in [m for m in sys.modules if m.startswith(("sage_plugins", "sage_worlds"))]:
        del sys.modules[name]


def server_for(host: PluginHost) -> SimpleNamespace:
    """The minimal server shape engine services (counters, emit) need."""
    return SimpleNamespace(events=host.events, redis=host.redis)
