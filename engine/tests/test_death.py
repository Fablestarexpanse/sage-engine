"""Player death: counters, afflictions stop at zero, and why the socket closed."""

from __future__ import annotations

import asyncio
import json
import time

import sage.commands.admin
import sage.commands.combat  # noqa: F401 — registers attack
from sage import app as app_module
from sage.effects.engine import make_effect, process_effects
from sage.network.session import Session, SessionManager
from tests.fakes import StubProtocol, StubSession, make_fake_server

ROOM = "z:gulch"


def test_dot_stops_once_dead():
    now = time.time()
    state = {"hp": 3, "max_hp": 10}
    eff = make_effect(
        "hazard.toxic",
        name="toxic",
        kind="dot",
        magnitude=5,
        interval=1.0,
        duration=30,
        now=now - 10,
    )
    state["effects"] = [eff]
    messages = process_effects(state, now=now)
    assert state["hp"] == 0
    assert sum("-5 hp" in m for m in messages) == 1


def test_combat_death_counts_and_ends_session():
    server = make_fake_server()
    saved = app_module.app_instance
    app_module.app_instance = server  # type: ignore[assignment]
    session = StubSession()
    try:

        async def run():
            await server.redis.set_player_location("tester", ROOM)
            await server.redis.set_player_stats("tester", {"hp": 1, "max_hp": 20})
            await server.redis.set_entity_state(
                "drone_1",
                {
                    "name": "drone",
                    "template": "drone",
                    "hp": 50,
                    "max_hp": 50,
                    "attack": 30,
                    "defense": 0,
                    "alive": True,
                },
            )
            await server.redis.add_entity_to_room("drone_1", ROOM)
            await server.dispatcher.dispatch(session, "attack drone")
            return await server.redis.get_player_stats("tester")

        stats = asyncio.run(run())
    finally:
        app_module.app_instance = saved
    assert stats["hp"] == 0
    assert stats["counters"]["deaths"] == 1
    assert session.end_reason == "died"


def test_quit_and_kick_tell_the_client_why():
    async def run():
        mgr = SessionManager()
        old_proto, quit_proto = StubProtocol(), StubProtocol()
        old = await mgr.create_session(old_proto)  # type: ignore[arg-type]
        mgr.link_player(old.id, "hana")
        await mgr.kick_existing("hana")
        quitter = Session("q1", quit_proto)  # type: ignore[arg-type]
        from sage.commands.admin import quit_cmd

        await quit_cmd(quitter, [])
        return old_proto.sent, quit_proto.sent, old_proto.closed, quit_proto.closed

    old_sent, quit_sent, old_closed, quit_closed = asyncio.run(run())

    def reasons(sent):
        out = []
        for line in sent:
            try:
                out.append(json.loads(line.strip()).get("reason"))
            except ValueError:
                pass
        return out

    assert reasons(old_sent) == ["replaced"] and old_closed
    assert reasons(quit_sent) == ["quit"] and quit_closed
