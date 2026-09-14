"""Regression guards for the SAGE brief's Phase -1 bugs (docs/sage/BRIEF.md §5).

All were already fixed in code when the brief arrived; these tests keep them fixed.
The fourth item (player client parsing only the first WebSocket frame) lives in
player-ui, which has no test runner; see docs/sage/PHASE0_AUDIT.md.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest import mock

import sage.app as app_module
import sage.commands.info
import sage.commands.movement  # noqa: F401
from sage.network.session import SessionManager
from sage.parser import dispatcher as dispatcher_mod
from sage.server import SageServer
from sage.world.models import ExitModel, RoomModel
from tests.fakes import StubProtocol, StubSession, make_fake_server

ROOM = "probe_zone:a"
ROOM_NORTH = "probe_zone:b"


def _server_with_rooms():
    server = make_fake_server()
    server.content_loader.rooms[ROOM] = RoomModel(
        id=ROOM,
        zone="probe_zone",
        type="chamber",
        description={"base": "Room A."},
        exits={"north": ExitModel(destination=ROOM_NORTH, description="North.")},
    )
    server.content_loader.rooms[ROOM_NORTH] = RoomModel(
        id=ROOM_NORTH,
        zone="probe_zone",
        type="chamber",
        description={"base": "Room B."},
        exits={"south": ExitModel(destination=ROOM, description="South.")},
    )
    return server


def test_move_reuses_the_server_dispatcher() -> None:
    """Brief item 1: a fresh CommandDispatcher in a handler bypasses hot reload.

    flee's half of this guard lives in engine/tests/plugins/test_combat_plugin.py.
    """

    async def run() -> None:
        server = _server_with_rooms()
        saved = app_module.app_instance
        app_module.app_instance = server  # type: ignore[assignment]
        try:
            session = StubSession()
            await server.redis.set_player_location("tester", ROOM)
            await server.redis.set_player_stats("tester", {"hp": 20})
            with mock.patch.object(
                dispatcher_mod.CommandDispatcher,
                "__init__",
                side_effect=AssertionError("handler built its own CommandDispatcher"),
            ):
                await server.dispatcher.dispatch(session, "north")
            assert "Room B." in "\n".join(session.sent)
        finally:
            app_module.app_instance = saved

    asyncio.run(run())


async def _loop_exit(disconnect_first: bool) -> set[str]:
    server = make_fake_server()
    server.session_manager = SessionManager()
    server.persistence = SimpleNamespace(sync_character=mock.AsyncMock())
    server._authenticate_websocket = mock.AsyncMock(return_value=None)
    session = await server.session_manager.create_session(StubProtocol())  # type: ignore[arg-type]
    server.session_manager.link_player(session.id, "tester")
    await server.redis.set_player_location("tester", ROOM)
    await server.redis.add_player_to_room("tester", ROOM)
    if disconnect_first:
        # Admin "disconnect" destroys the session before the loop's finally runs.
        await server.session_manager.destroy_session(session.id)
    await SageServer.run_session_loop(server, session)  # type: ignore[arg-type]
    return set(await server.redis.get_room_players(ROOM))


def test_leaving_the_game_leaves_the_room() -> None:
    """Brief item 2: ghost players left in room sets after a session ends."""
    assert "tester" not in asyncio.run(_loop_exit(disconnect_first=False))


def test_admin_disconnect_also_leaves_the_room() -> None:
    assert "tester" not in asyncio.run(_loop_exit(disconnect_first=True))
