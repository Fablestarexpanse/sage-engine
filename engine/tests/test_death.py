"""Player death: counters, afflictions stop at zero, and why the socket closed."""

from __future__ import annotations

import asyncio
import json
import time

import sage.commands.admin  # noqa: F401
from sage.effects.engine import make_effect, process_effects
from sage.network.session import Session, SessionManager
from tests.fakes import StubProtocol


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
