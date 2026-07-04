"""Session state machine and SessionManager lifecycle."""

from __future__ import annotations

import asyncio
import unittest

from fablestar.network.session import Session, SessionManager, SessionState
from tests.fakes import StubProtocol


class TestSession(unittest.TestCase):
    def test_send_appends_newline(self) -> None:
        asyncio.run(self._send_appends())

    async def _send_appends(self) -> None:
        proto = StubProtocol()
        session = Session("s1", proto)  # type: ignore[arg-type]
        await session.send("hello")
        self.assertEqual(proto.sent, ["hello\r\n"])

    def test_send_skipped_when_disconnected(self) -> None:
        asyncio.run(self._send_skipped())

    async def _send_skipped(self) -> None:
        proto = StubProtocol()
        proto._connected = False
        session = Session("s1", proto)  # type: ignore[arg-type]
        await session.send("hello")
        self.assertEqual(proto.sent, [])

    def test_close_transitions_state(self) -> None:
        asyncio.run(self._close_transitions())

    async def _close_transitions(self) -> None:
        proto = StubProtocol()
        session = Session("s1", proto)  # type: ignore[arg-type]
        self.assertEqual(session.state, SessionState.CONNECTED)
        await session.close()
        self.assertEqual(session.state, SessionState.DISCONNECTING)
        self.assertTrue(proto.closed)


class TestSessionManager(unittest.TestCase):
    def test_create_session_tracks(self) -> None:
        asyncio.run(self._create_tracks())

    async def _create_tracks(self) -> None:
        mgr = SessionManager()
        session = await mgr.create_session(StubProtocol())  # type: ignore[arg-type]
        self.assertIn(session.id, mgr.sessions)
        self.assertEqual(session.state, SessionState.CONNECTED)

    def test_link_player(self) -> None:
        asyncio.run(self._link_player())

    async def _link_player(self) -> None:
        mgr = SessionManager()
        session = await mgr.create_session(StubProtocol())  # type: ignore[arg-type]
        mgr.link_player(session.id, "alice")
        self.assertEqual(session.player_id, "alice")
        self.assertEqual(session.state, SessionState.PLAYING)
        self.assertIs(mgr.get_session_by_player("alice"), session)

    def test_get_session_by_player_missing(self) -> None:
        mgr = SessionManager()
        self.assertIsNone(mgr.get_session_by_player("nobody"))

    def test_destroy_session_removes_both_mappings(self) -> None:
        asyncio.run(self._destroy_removes())

    async def _destroy_removes(self) -> None:
        mgr = SessionManager()
        proto = StubProtocol()
        session = await mgr.create_session(proto)  # type: ignore[arg-type]
        mgr.link_player(session.id, "bob")
        await mgr.destroy_session(session.id)
        self.assertNotIn(session.id, mgr.sessions)
        self.assertIsNone(mgr.get_session_by_player("bob"))
        self.assertTrue(proto.closed)

    def test_broadcast_skips_non_playing(self) -> None:
        asyncio.run(self._broadcast_skips())

    async def _broadcast_skips(self) -> None:
        mgr = SessionManager()
        playing_proto = StubProtocol()
        idle_proto = StubProtocol()
        playing = await mgr.create_session(playing_proto)  # type: ignore[arg-type]
        await mgr.create_session(idle_proto)  # stays CONNECTED
        mgr.link_player(playing.id, "carol")
        await mgr.broadcast("hi all")
        self.assertEqual(playing_proto.sent, ["hi all\r\n"])
        self.assertEqual(idle_proto.sent, [])

    def test_broadcast_exclude(self) -> None:
        asyncio.run(self._broadcast_exclude())

    async def _broadcast_exclude(self) -> None:
        mgr = SessionManager()
        p1, p2 = StubProtocol(), StubProtocol()
        s1 = await mgr.create_session(p1)  # type: ignore[arg-type]
        s2 = await mgr.create_session(p2)  # type: ignore[arg-type]
        mgr.link_player(s1.id, "dave")
        mgr.link_player(s2.id, "erin")
        await mgr.broadcast("psst", exclude={s1.id})
        self.assertEqual(p1.sent, [])
        self.assertEqual(p2.sent, ["psst\r\n"])


if __name__ == "__main__":
    unittest.main()
