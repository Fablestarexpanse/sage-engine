"""Plugin loader: discovery, ordering, trust, seal, API surface, teardown (contracts Part C)."""

from __future__ import annotations

import asyncio
import logging
import sys
import textwrap
from pathlib import Path

import pytest

from sage.commands.registry import CommandRegistry
from sage.core.events import EventBus, PlayerDied
from sage.core.resolvers import Resolvers
from sage.core.tick import TickManager
from sage.plugins import PluginError, PluginHost
from sage.plugins.loader import order
from sage.plugins.manifest import caret, read_manifest
from sage.world.package import load_world_package
from tests.fakes import FakeRedis

WORLD_TOML = """
[world]
id = "demo"
name = "Demo"
version = "1.0.0"
engine = ">=0.1"

[start]
room = "town:gate"
respawn = "town:gate"

[plugins]
{plugins}

[params]
"greeter.greeting" = "Well met"
"""

PLUGIN_TOML = """
[plugin]
id = "{id}"
version = "{version}"
engine = "{engine}"
entry = "{pkg}.main:setup"
first_party = {first_party}

[depends]
{depends}

[touches]
{touches}
"""


def write_world(root: Path, plugins: dict[str, str]) -> Path:
    world = root / "worlds" / "demo"
    (world / "content").mkdir(parents=True)
    lines = "\n".join(f'{k} = "{v}"' for k, v in plugins.items())
    (world / "world.toml").write_text(WORLD_TOML.format(plugins=lines), encoding="utf-8")
    (world / "stats.yaml").write_text("{}\n", encoding="utf-8")
    (world / "currencies.yaml").write_text("[]\n", encoding="utf-8")
    return world


def write_plugin(
    base: Path,
    plugin_id: str,
    body: str,
    *,
    touches: str = "",
    depends: str = "",
    version: str = "1.0.0",
    engine: str = ">=0.1",
    first_party: bool = True,
    lexicon: str | None = None,
) -> Path:
    pkg = f"sage_plugin_{plugin_id}"
    plugin = base / plugin_id
    (plugin / pkg).mkdir(parents=True)
    (plugin / "plugin.toml").write_text(
        PLUGIN_TOML.format(
            id=plugin_id,
            version=version,
            engine=engine,
            pkg=pkg,
            first_party=str(first_party).lower(),
            depends=depends,
            touches=touches,
        ),
        encoding="utf-8",
    )
    (plugin / pkg / "__init__.py").write_text("", encoding="utf-8")
    (plugin / pkg / "main.py").write_text(textwrap.dedent(body), encoding="utf-8")
    if lexicon is not None:
        (plugin / "lexicon").mkdir()
        (plugin / "lexicon" / "en.yaml").write_text(lexicon, encoding="utf-8")
    return plugin


@pytest.fixture
def host_for(tmp_path):
    hosts: list[PluginHost] = []

    def build(plugins: dict[str, str]) -> PluginHost:
        world = load_world_package(write_world(tmp_path, plugins))
        host = PluginHost(
            world=world,
            registry=CommandRegistry(),
            events=EventBus(),
            resolvers=Resolvers(),
            tick_manager=TickManager(tick_rate=0.25),
            redis=FakeRedis(),
            plugins_root=tmp_path / "plugins",
            trusted_roots=[tmp_path / "plugins", tmp_path / "worlds"],
        )
        hosts.append(host)
        return host

    yield build
    for host in hosts:
        host.teardown()
    for name in [m for m in sys.modules if m.startswith(("sage_plugins", "sage_worlds"))]:
        del sys.modules[name]


GREETER = """
from sage.core.events import PlayerDied

seen = []

def setup(api):
    async def greet(session, args):
        await session.send(api.t("greeter.hello", greeting=api.param("greeting", "Hi")))
    api.commands.register("greet", greet, aliases=["hi"])
    api.events.subscribe(PlayerDied, seen.append)
    api.resolvers.provide("death.check", lambda stats: False)
    api.state.block("greeter")

def teardown(api):
    seen.append("torn down")
"""

GREETER_TOUCHES = """
commands = ["greet"]
events_subscribe = ["PlayerDied"]
resolvers = ["death.check"]
state_blocks = ["greeter"]
lexicon_prefix = "greeter."
"""


def test_loads_registers_and_tears_down(tmp_path, host_for):
    write_plugin(
        tmp_path / "plugins",
        "greeter",
        GREETER,
        touches=GREETER_TOUCHES,
        lexicon="greeter:\n  hello: '{greeting}, traveller.'\n",
    )
    host = host_for({"greeter": "^1"})
    host.resolvers.define("death.check", lambda stats: True)
    [record] = host.load()

    assert host.registry.get("hi").name == "greet"
    assert host.events.subscribers(PlayerDied) == ["greeter"]
    assert host.resolvers.get("death.check")({"hp": 0}) is False
    assert host.lexicon_layers() == [
        ("plugin:greeter", {"greeter.hello": "{greeting}, traveller."})
    ]

    module = sys.modules["sage_plugins.greeter.sage_plugin_greeter.main"]
    host.teardown()
    assert module.seen == ["torn down"]
    assert host.registry.get("greet") is None
    assert host.events.subscribers(PlayerDied) == []
    assert host.resolvers.get("death.check")({"hp": 0}) is True


def test_undeclared_registration_fails_boot_and_rolls_back(tmp_path, host_for):
    write_plugin(
        tmp_path / "plugins",
        "sneaky",
        """
        def setup(api):
            async def noop(session, args): ...
            api.commands.register("allowed", noop)
            api.commands.register("hidden", noop)
        """,
        touches='commands = ["allowed"]',
    )
    host = host_for({"sneaky": "^1"})
    with pytest.raises(PluginError, match=r"registered commands \['hidden'\] not declared"):
        host.load()
    assert host.registry.get("allowed") is None and host.registry.get("hidden") is None


def test_dependency_order_and_missing_dependency(tmp_path, host_for):
    noop = "def setup(api):\n    pass\n"
    write_plugin(tmp_path / "plugins", "base", noop)
    write_plugin(tmp_path / "plugins", "addon", noop, depends='base = "^1"')
    write_plugin(
        tmp_path / "plugins", "extra", noop, depends='ghost = { version = "^1", optional = true }'
    )
    host = host_for({"addon": "^1", "base": "^1", "extra": "^1"})
    assert [r.id for r in host.load()] == ["base", "addon", "extra"]

    other = tmp_path / "second"
    write_plugin(other / "plugins", "addon", noop, depends='base = "^1"')
    world = load_world_package(write_world(other, {"addon": "^1"}))
    lonely = PluginHost(
        world,
        CommandRegistry(),
        EventBus(),
        Resolvers(),
        TickManager(),
        FakeRedis(),
        other / "plugins",
        [other],
    )
    with pytest.raises(PluginError, match="requires base"):
        lonely.load()


def test_cycles_are_rejected():
    class Rec:
        def __init__(self, pid, deps):
            self.id = pid
            self.manifest = type("M", (), {"depends": dict.fromkeys(deps)})()

    with pytest.raises(PluginError, match="cycle among: a, b"):
        order({"a": Rec("a", ["b"]), "b": Rec("b", ["a"])})


def test_version_ranges_are_enforced(tmp_path, host_for):
    write_plugin(tmp_path / "plugins", "old", "def setup(api):\n    pass\n", version="0.9.0")
    with pytest.raises(PluginError, match="wants plugin old"):
        host_for({"old": "^1"}).load()


def test_engine_range_is_enforced(tmp_path, host_for):
    write_plugin(tmp_path / "plugins", "future", "def setup(api):\n    pass\n", engine=">=99")
    with pytest.raises(PluginError, match="needs engine"):
        host_for({"future": "^1"}).load()


def test_world_private_plugin_shadows_first_party(tmp_path, host_for):
    write_plugin(tmp_path / "plugins", "twin", "def setup(api):\n    api.log.info('first')\n")
    write_plugin(
        tmp_path / "worlds" / "demo" / "plugins",
        "twin",
        "def setup(api):\n    pass\n",
        version="1.1.0",
    )
    host = host_for({"twin": "^1"})
    [record] = host.load()
    assert record.module_base == "sage_worlds.demo.plugins.twin"
    assert record.manifest.plugin.version == "1.1.0"


def test_untrusted_plugin_logs_a_loud_banner(tmp_path, host_for, caplog):
    write_plugin(tmp_path / "plugins", "outsider", "def setup(api):\n    pass\n", first_party=False)
    host = host_for({"outsider": "^1"})
    with caplog.at_level(logging.WARNING, logger="sage.plugins.loader"):
        host.load()
    assert "LOADING NON-FIRST-PARTY PLUGIN outsider" in caplog.text


def test_lexicon_keys_must_use_the_plugin_prefix(tmp_path, host_for):
    write_plugin(
        tmp_path / "plugins",
        "chatty",
        "def setup(api):\n    pass\n",
        touches='lexicon_prefix = "chatty."',
        lexicon="who:\n  empty: 'hijacked'\n",
    )
    with pytest.raises(PluginError, match="outside 'chatty.'"):
        host_for({"chatty": "^1"}).load()


def test_services_need_a_declared_dependency(tmp_path, host_for):
    write_plugin(
        tmp_path / "plugins",
        "clock",
        "def setup(api):\n    api.services.provide('clock', object())\n",
        touches='services = ["clock"]',
    )
    write_plugin(
        tmp_path / "plugins",
        "reader",
        "def setup(api):\n    api.services.get('clock')\n",
    )
    with pytest.raises(PluginError, match="without depending on it"):
        host_for({"clock": "^1", "reader": "^1"}).load()


def test_state_blocks_and_params(tmp_path, host_for):
    write_plugin(
        tmp_path / "plugins",
        "greeter",
        "def setup(api):\n    api.state.block('greeter', default=lambda: {'visits': 0})\n",
        touches='state_blocks = ["greeter"]',
    )
    host = host_for({"greeter": "^1"})
    [record] = host.load()
    api = record.api

    async def run():
        assert await api.state.get("p1", "greeter") == {"visits": 0}
        await api.state.set("p1", "greeter", {"visits": 2})
        assert (await host.redis.get_player_stats("p1"))["greeter"] == {"visits": 2}
        with pytest.raises(PluginError, match="did not register"):
            await api.state.get("p1", "other")

    asyncio.run(run())
    assert api.param("greeting") == "Well met"


def test_manifest_helpers(tmp_path):
    assert caret("^1") == ">=1.0.0,<2"
    assert caret("^2.3") == ">=2.3.0,<3"
    plugin = write_plugin(tmp_path, "named", "def setup(api):\n    pass\n")
    renamed = plugin.rename(tmp_path / "other")
    with pytest.raises(PluginError, match="must match its directory"):
        read_manifest(renamed)
