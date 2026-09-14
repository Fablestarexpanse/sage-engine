"""In-game staff commands: hidden from players, gated by the staff account's tools, audited."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sage import app as app_module
from sage import lexicon
from sage.admin.admin_security import AdminContext
from sage.commands.registry import registry
from sage.network.session import SessionManager
from sage.parser.dispatcher import _resolve_verb
from sage.world.models import RoomModel
from tests.fakes import StubSession, make_fake_server

registry.load_module_strict("sage.commands.staff")
registry.load_module_strict("sage.commands.info")

STAFF_VERBS = ("goto", "at", "where", "stat", "transfer", "restore", "mute", "unmute", "staff")


def _ctx(tools=None, role="gm", zones=None):
    perms = {}
    if tools is not None:
        perms["tools"] = tools
    if zones is not None:
        perms["zones"] = zones
    return AdminContext(
        staff_id=5,
        username="gm_ann",
        display_name="Ann",
        role=role,
        permissions=perms,
        bypass_auth=False,
    )


@pytest.fixture()
def world(monkeypatch):
    """A server with two rooms, a staff member (Ann) and a player (Bo) connected."""
    from sage.admin import audit
    from sage.services import staff_powers

    server = make_fake_server()
    server.session_manager = SessionManager()
    ann, bo = StubSession("Ann"), StubSession("Bo")
    bo.id = "session-bo"
    server.session_manager.sessions = {ann.id: ann, bo.id: bo}
    server.session_manager.player_to_session = {"Ann": ann.id, "Bo": bo.id}
    for room_id in ("town:inn", "town:gate"):
        server.content_loader.rooms[room_id] = RoomModel(
            id=room_id, zone="town", name=room_id, type="hub", depth=0
        )
    staff = {"Ann": _ctx(["players", "world"])}
    recorded = []

    async def fake_staff_context(_server, session):
        return staff.get(session.player_id)

    async def fake_record(_server, ctx, action, target, **detail):
        recorded.append((ctx.username, action, target))

    monkeypatch.setattr(staff_powers, "staff_context", fake_staff_context)
    monkeypatch.setattr(audit, "record", fake_record)
    saved = app_module.app_instance
    app_module.app_instance = server  # type: ignore[assignment]
    try:
        yield SimpleNamespace(server=server, ann=ann, bo=bo, staff=staff, recorded=recorded)
    finally:
        app_module.app_instance = saved


def _run(server, session, line):
    asyncio.run(server.dispatcher.dispatch(session, line))


def test_staff_commands_are_hidden_from_players():
    names = registry.names()
    assert not set(STAFF_VERBS) & set(names)
    assert set(STAFF_VERBS) <= set(registry.names(include_staff=True))
    assert _resolve_verb("transf")[0] is None  # no prefix match onto a staff command
    assert "goto" not in _resolve_verb("gotx")[1]


def test_a_player_without_staff_power_sees_an_unknown_command(world):
    _run(world.server, world.bo, "goto town:gate")
    assert world.bo.sent == [lexicon.t("parser.unknown_command", verb="goto", hint="")]
    _run(world.server, world.bo, "help")
    assert not any("goto" in line for line in world.bo.sent[1:])
    assert world.recorded == []


def test_staff_tools_decide_what_a_gm_may_do(world):
    world.staff["Ann"] = _ctx(["dashboard"])
    _run(world.server, world.ann, "goto town:gate")
    assert world.ann.sent[-1] == lexicon.t("staffcmd.tool_denied", verb="goto")
    world.staff["Ann"] = _ctx(["world"], zones=["harbor"])
    _run(world.server, world.ann, "goto town:gate")
    assert world.ann.sent[-1] == lexicon.t("staffcmd.zone_denied", room="town:gate")
    assert world.recorded == []


def test_goto_moves_the_staff_member_tells_both_rooms_and_is_audited(world):
    server = world.server

    async def setup():
        await server.redis.set_player_location("Ann", "town:inn")
        await server.redis.set_player_location("Bo", "town:gate")

    asyncio.run(setup())
    _run(server, world.ann, "goto town:gate")  # by character name needs the database: live test
    assert asyncio.run(server.redis.get_player_location("Ann")) == "town:gate"
    assert lexicon.t("staffcmd.appears", name="Ann") in world.bo.sent
    assert world.recorded == [("gm_ann", "ingame.goto", "town:gate")]


def test_where_lists_who_is_online(world):
    server = world.server

    async def setup():
        await server.redis.set_player_location("Ann", "town:inn")
        await server.redis.set_player_location("Bo", "town:gate")

    asyncio.run(setup())
    _run(server, world.ann, "where")
    out = world.ann.sent[-1]
    assert "Bo - town:gate" in out and "Ann - town:inn" in out


def test_at_runs_one_command_elsewhere_and_comes_back(world):
    server = world.server

    async def setup():
        await server.redis.set_player_location("Ann", "town:inn")

    asyncio.run(setup())
    _run(server, world.ann, "at town:gate who")
    assert asyncio.run(server.redis.get_player_location("Ann")) == "town:inn"
    assert world.recorded == [("gm_ann", "ingame.at", "town:gate")]
    _run(server, world.ann, "at town:gate goto town:inn")
    assert world.ann.sent[-1] == lexicon.t("staffcmd.at_usage")
