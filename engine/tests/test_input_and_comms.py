"""Dispatcher input hygiene (control chars, length, rate, prefixes) and free-text comms."""

from __future__ import annotations

import asyncio

from sage import app as app_module
from sage.commands.communication import resolve_tell_target
from sage.network.session import SessionManager
from sage.parser.dispatcher import MAX_INPUT_CHARS, RATE_BURST, _resolve_verb, clean_input
from tests.fakes import StubSession, make_fake_server

ONLINE = ["Qa Tester", "Qa Watcher", "Tessa Moke", "Old Pell"]


def test_clean_input_strips_ansi_and_caps_length():
    assert clean_input("say \x1b[31mred\x1b[0m") == "say [31mred[0m"
    assert clean_input("say line one\nline two") == "say line one line two"
    assert len(clean_input("x" * 10_000)) == MAX_INPUT_CHARS


def test_unique_prefix_and_suggestions():
    cmd, _ = _resolve_verb("inven")
    assert cmd is not None and cmd.name == "inventory"
    cmd, sugg = _resolve_verb("lok")
    assert cmd is None and "look" in sugg


def test_tell_resolution():
    assert resolve_tell_target("Tessa Moke hello there".split(), ONLINE, "Qa Watcher") == (
        "Tessa Moke",
        "hello there",
        None,
    )
    assert resolve_tell_target("tessa hi".split(), ONLINE, "Qa Watcher")[:2] == ("Tessa Moke", "hi")
    assert resolve_tell_target("qa hello".split(), ONLINE, "Qa Watcher")[:2] == (
        "Qa Tester",
        "hello",
    )
    assert resolve_tell_target("Qa Tester are you there".split(), ONLINE, "Qa Watcher")[:2] == (
        "Qa Tester",
        "are you there",
    )
    assert resolve_tell_target("Qa Watcher note".split(), ONLINE, "Qa Watcher")[2] == "self"
    assert resolve_tell_target("qa hi".split(), ONLINE, "Old Pell")[2] == [
        "Qa Tester",
        "Qa Watcher",
    ]
    assert resolve_tell_target("nobody hi".split(), ONLINE, "Old Pell")[2] == "nobody"


def _server_with_two_players():
    server = make_fake_server()
    server.session_manager = SessionManager()
    speaker, listener = StubSession("Qa Tester"), StubSession("Qa Watcher")
    listener.id = "session-listener"
    server.session_manager.sessions = {speaker.id: speaker, listener.id: listener}
    server.session_manager.player_to_session = {"Qa Tester": speaker.id, "Qa Watcher": listener.id}
    return server, speaker, listener


def test_say_and_tell_keep_case():
    server, speaker, listener = _server_with_two_players()
    saved = app_module.app_instance
    app_module.app_instance = server  # type: ignore[assignment]
    try:

        async def run():
            await server.redis.set_player_location("Qa Tester", "z:r")
            await server.redis.set_player_location("Qa Watcher", "z:r")
            await server.dispatcher.dispatch(speaker, "say Mixed CASE Words")
            await server.dispatcher.dispatch(speaker, "tell Qa Watcher Hello There")

        asyncio.run(run())
    finally:
        app_module.app_instance = saved
    heard = "\n".join(listener.sent)
    assert 'Qa Tester says: "Mixed CASE Words"' in heard
    assert 'Qa Tester tells you: "Hello There"' in heard


def test_flood_is_throttled_once():
    server = make_fake_server()
    session = StubSession()

    async def run():
        for _ in range(int(RATE_BURST) + 30):
            await server.dispatcher.dispatch(session, "xyzzy")

    asyncio.run(run())
    unknown = [m for m in session.sent if m.startswith("Unknown command")]
    slow = [m for m in session.sent if m.startswith("Slow down")]
    assert len(unknown) <= RATE_BURST + 1
    assert len(slow) == 1


def test_look_with_target_examines_and_movement_announces():
    import sage.commands.items
    import sage.commands.movement  # noqa: F401
    from sage.world.models import RoomModel

    server, mover, watcher = _server_with_two_players()
    server.content_loader.rooms = {
        "z:a": RoomModel(
            id="z:a",
            zone="z",
            type="chamber",
            name="A",
            exits={"north": {"destination": "z:b", "description": "A ramp climbs north."}},
        ),
        "z:b": RoomModel(
            id="z:b",
            zone="z",
            type="chamber",
            name="B",
            exits={"south": {"destination": "z:a", "description": "Back down."}},
        ),
    }
    saved = app_module.app_instance
    app_module.app_instance = server  # type: ignore[assignment]
    try:

        async def run():
            await server.redis.set_player_location("Qa Tester", "z:a")
            await server.redis.set_player_location("Qa Watcher", "z:a")
            await server.dispatcher.dispatch(mover, "look north")
            await server.dispatcher.dispatch(mover, "look at qa watcher")
            await server.dispatcher.dispatch(mover, "north")

        asyncio.run(run())
    finally:
        app_module.app_instance = saved
    said = "\n".join(mover.sent)
    assert "A ramp climbs north." in said
    assert "Qa Watcher looks unhurt." in said
    assert "Qa Tester leaves north." in watcher.sent
