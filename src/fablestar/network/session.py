"""Session state machine (CONNECTED → AUTHENTICATING → PLAYING → DISCONNECTING) and SessionManager."""

import logging
import uuid
from enum import Enum, auto

from fablestar.network.websocket_protocol import WebSocketProtocol

logger = logging.getLogger(__name__)


class SessionState(Enum):
    CONNECTED = auto()
    AUTHENTICATING = auto()
    PLAYING = auto()
    DISCONNECTING = auto()


class Session:
    """
    Represents an active connection to the server.
    Bridges the network layer to the player state.
    """

    def __init__(self, session_id: str, protocol: WebSocketProtocol):
        self.id = session_id
        self.protocol = protocol
        self.state = SessionState.CONNECTED
        self.player_id: str | None = None
        self.last_activity = 0.0  # Will be updated with monotonic time

    async def send(self, message: str):
        """Send raw text to the client, adding a newline."""
        if self.protocol.is_connected:
            # Automatic newline append for MUD feel
            await self.protocol.send(message + "\r\n")

    async def send_prompt(self):
        """Send the command prompt to the client (no newline)."""
        if self.protocol.is_connected:
            prompt = "\r\n> "  # Default prompt
            await self.protocol.send(prompt)

    async def close(self):
        """Gracefully close the session."""
        self.state = SessionState.DISCONNECTING
        await self.protocol.close()


class SessionManager:
    """Manages all active player sessions.

    Async methods (destroy_session, broadcast) perform I/O; create_session is
    async only for interface symmetry — it just registers the session in memory.
    Sync methods (get_session_by_player, link_player) are in-memory lookups
    and are intentionally synchronous — they do no I/O.
    """

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.player_to_session: dict[str, str] = {}

    async def create_session(self, protocol: WebSocketProtocol) -> Session:
        """Create and track a new session."""
        session_id = str(uuid.uuid4())
        session = Session(session_id, protocol)
        self.sessions[session_id] = session
        logger.info(f"New session created: {session_id} from {protocol.peer_info}")
        return session

    async def destroy_session(self, session_id: str):
        """Remove a session from tracking."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if session.player_id and session.player_id in self.player_to_session:
                del self.player_to_session[session.player_id]

            await session.close()
            del self.sessions[session_id]
            logger.info(f"Session destroyed: {session_id}")

    def get_session_by_player(self, player_id: str) -> Session | None:
        """Find an active session for a specific player ID."""
        session_id = self.player_to_session.get(player_id)
        if session_id:
            return self.sessions.get(session_id)
        return None

    async def kick_existing(self, player_id: str) -> bool:
        """One session per character: close any live session already playing it."""
        old_id = self.player_to_session.get(player_id)
        if not old_id or old_id not in self.sessions:
            return False
        old = self.sessions[old_id]
        try:
            await old.send("\r\nThis character just signed in from another connection. Goodbye.")
        except Exception:
            pass
        # Don't touch Redis room state — the new session inherits the same
        # character position; only the old socket dies.
        self.player_to_session.pop(player_id, None)
        try:
            await old.close()
        except Exception:
            pass
        self.sessions.pop(old_id, None)
        logger.info("Kicked prior session %s for %s (new login)", old_id, player_id)
        return True

    def link_player(self, session_id: str, player_id: str):
        """Link a session to a player ID once authenticated."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.player_id = player_id
            session.state = SessionState.PLAYING
            self.player_to_session[player_id] = session_id

    async def broadcast(self, message: str, exclude: set[str] | None = None):
        """Send a message to all playing sessions."""
        exclude = exclude or set()
        for session in self.sessions.values():
            if session.state == SessionState.PLAYING and session.id not in exclude:
                await session.send(message)
