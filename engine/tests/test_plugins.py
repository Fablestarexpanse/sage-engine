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


NOTICES = """
from pydantic import BaseModel

from sage.api import PluginAPI


class NoticeBoard(BaseModel):
    title: str
    posts: list[str] = []


def setup(api: PluginAPI) -> None:
    api.content.extend("room", "notice_board", NoticeBoard)

    async def read(session, args):
        room = api.content.room(args[0])
        board = api.content.extension(room, "room", "notice_board")
        await session.send(board.title if board else "no board")

    api.commands.register("notices", read)
"""


def _room(world_dir: Path, slug: str, extra: str) -> None:
    rooms = world_dir / "content" / "world" / "zones" / "town" / "rooms"
    rooms.mkdir(parents=True, exist_ok=True)
    body = f"id: town:{slug}\nzone: town\ntype: hub\n{extra}"
    (rooms / f"{slug}.yaml").write_text(body, encoding="utf-8")


def test_plugin_claims_a_room_field_and_reads_it_validated(tmp_path, host_for, caplog):
    from sage.world.loader import ContentLoader
    from tests.fakes import StubSession

    write_plugin(
        tmp_path / "plugins",
        "notices",
        NOTICES,
        touches='commands = ["notices"]\ncontent_extensions = ["room.notice_board"]',
    )
    host = host_for({"notices": "^1"})
    _room(host.world.root, "gate", "notice_board:\n  title: Wanted\n  posts: [rats]\n")
    _room(host.world.root, "well", "notice_board:\n  posts: [no title]\n")
    _room(host.world.root, "lane", "")
    host.content = ContentLoader(host.world.content_dir)
    host.load()

    session = StubSession("hero")
    handler = host.registry.get("notices").handler
    with caplog.at_level(logging.ERROR):
        for slug in ("gate", "well", "lane"):
            asyncio.run(handler(session, [f"town:{slug}"]))
    assert session.sent == ["Wanted", "no board", "no board"]
    assert "town:well: invalid 'notice_board' block" in caplog.text
    assert "room.notice_board" in host.extensions.schemas()


def test_extensions_must_be_declared_unique_and_not_engine_fields(tmp_path, host_for):
    write_plugin(tmp_path / "plugins", "notices", NOTICES, touches='commands = ["notices"]')
    with pytest.raises(PluginError, match="content_extensions"):
        host_for({"notices": "^1"}).load()

    from pydantic import BaseModel

    from sage.world.extensions import ContentExtensions, ExtensionError

    class Board(BaseModel):
        title: str

    registry = ContentExtensions()
    registry.register("room", "notice_board", Board, owner="a")
    with pytest.raises(ExtensionError, match="already claimed by a"):
        registry.register("room", "notice_board", Board, owner="b")
    with pytest.raises(ExtensionError, match="engine field"):
        registry.register("room", "exits", Board, owner="a")
    with pytest.raises(ExtensionError, match="unknown content kind"):
        registry.register("zone", "x", Board, owner="a")
    registry.withdraw("a")
    registry.register("room", "notice_board", Board, owner="b")


LEDGER = """
from fastapi import APIRouter

from sage.api import PluginAPI


def setup(api: PluginAPI) -> None:
    router = APIRouter()

    @router.get("/ledger")
    async def ledger():
        return {"rows": 3}

    api.http.admin_router(router, tool="shops")
"""


def _app_with_staff(tools):
    from fastapi import FastAPI

    from sage.admin.admin_security import AdminContext

    app = FastAPI()

    @app.middleware("http")
    async def staff(request, call_next):
        request.state.admin_ctx = AdminContext(
            staff_id=1, username="s", display_name="S", role="staff", permissions={"tools": tools}
        )
        return await call_next(request)

    return app


def test_plugin_admin_routes_mount_under_their_prefix_behind_a_tool(tmp_path, host_for):
    from fastapi.testclient import TestClient

    write_plugin(tmp_path / "plugins", "ledgers", LEDGER, touches='routes = ["/plugins/ledgers/*"]')
    host = host_for({"ledgers": "^1"})
    host.http = _app_with_staff(["shops"])
    host.load()
    client = TestClient(host.http)
    assert client.get("/plugins/ledgers/admin/ledger").json() == {"rows": 3}

    denied = _app_with_staff(["agents"])
    denied.router.routes[:] = host.http.router.routes
    assert TestClient(denied).get("/plugins/ledgers/admin/ledger").status_code == 403

    host.teardown()
    assert client.get("/plugins/ledgers/admin/ledger").status_code == 404


def test_plugin_routes_must_be_declared_under_their_own_prefix(tmp_path, host_for):
    write_plugin(tmp_path / "plugins", "ledgers", LEDGER, touches="")
    host = host_for({"ledgers": "^1"})
    host.http = _app_with_staff(["shops"])
    with pytest.raises(PluginError, match="routes"):
        host.load()
    bad = tmp_path / "bad"
    write_plugin(bad, "ledgers", LEDGER, touches='routes = ["/admin/*"]')
    with pytest.raises(PluginError, match="may only declare"):
        read_manifest(bad / "ledgers")


COUNTER = """
from sage.api import PluginAPI


def setup(api: PluginAPI) -> None:
    async def poke(session, args):
        await api.redis.incrby(args[0], 1)

    api.commands.register("poke", poke)
"""


def test_plugin_redis_keys_stay_inside_declared_prefixes(tmp_path, host_for):
    from tests.fakes import StubSession

    write_plugin(
        tmp_path / "plugins",
        "pokes",
        COUNTER,
        touches='commands = ["poke"]\nredis_prefixes = ["pokes"]',
    )
    host = host_for({"pokes": "^1"})
    host.load()
    handler = host.registry.get("poke").handler
    asyncio.run(handler(StubSession("hero"), ["pokes:hero"]))
    assert host.redis.client.strings["pokes:hero"] == "1"
    with pytest.raises(PluginError, match="outside its redis_prefixes"):
        asyncio.run(handler(StubSession("hero"), ["player:hero:stats"]))

    reserved = tmp_path / "reserved"
    write_plugin(reserved, "pokes", COUNTER, touches='redis_prefixes = ["player"]')
    with pytest.raises(PluginError, match="reserved for the engine"):
        read_manifest(reserved / "pokes")


PUPPETEER = """
from sage.api import PluginAPI, VirtualSession


def setup(api: PluginAPI) -> None:
    api.characters.claim_names(lambda: ["Puppet Pam"])

    async def flush():
        api.log.info("flushed")

    api.persistence.on_flush(flush)

    async def spawn(session, args):
        pam = VirtualSession("Puppet Pam")
        api.sessions.attach(pam)
        await api.characters.place("Puppet Pam", {"hp": 5}, [], "town:gate")
        stats = await api.characters.stats("Puppet Pam")
        stats["hp"] = 4
        await api.characters.save_stats("Puppet Pam", stats)
        await api.sessions.dispatch(pam, "wave")

    async def scribble(session, args):
        await api.characters.save_stats("hero", {"hp": 0})

    api.commands.register("spawn", spawn)
    api.commands.register("scribble", scribble)
"""


def test_plugins_run_virtual_characters_they_place(tmp_path, host_for):
    from types import SimpleNamespace

    from tests.fakes import StubSession

    write_plugin(
        tmp_path / "plugins", "puppets", PUPPETEER, touches='commands = ["spawn", "scribble"]'
    )
    host = host_for({"puppets": "^1"})
    dispatched: list[tuple[str, str]] = []

    async def dispatch(session, line):
        dispatched.append((session.player_id, line))

    flush_hooks: list = []
    host.server = SimpleNamespace(
        session_manager=SimpleNamespace(sessions={}, player_to_session={}),
        dispatcher=SimpleNamespace(dispatch=dispatch),
        persistence=SimpleNamespace(flush_hooks=flush_hooks),
    )
    host.load()
    asyncio.run(host.registry.get("spawn").handler(StubSession("admin"), []))

    manager = host.server.session_manager
    session_id = manager.player_to_session["Puppet Pam"]
    assert manager.sessions[session_id].virtual is True
    assert host.redis.stats["Puppet Pam"] == {"hp": 4}
    assert host.redis.locations["Puppet Pam"] == "town:gate"
    assert dispatched == [("Puppet Pam", "wave")]
    assert len(flush_hooks) == 1
    assert [sorted(fn()) for _, fn in host.name_claims] == [["Puppet Pam"]]

    with pytest.raises(PluginError, match="did not place"):
        asyncio.run(host.registry.get("scribble").handler(StubSession("admin"), []))

    host.teardown()
    assert manager.player_to_session == {} and flush_hooks == [] and host.name_claims == []


def test_progression_slot_defaults_let_a_world_run_without_progression():
    from sage.world.progression import (
        default_seed_attributes,
        default_skill_sheet,
        default_total_levels,
    )

    stats: dict = {}
    default_seed_attributes(stats, {"might": 3})
    assert stats == {"might": 3}
    assert default_total_levels(stats) == 0
    assert default_skill_sheet(stats) == {"attributes": {}, "leaves": []}
