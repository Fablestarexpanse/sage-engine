"""Virtual sessions: a character driven by code instead of a socket.

A VirtualSession has the same contract as a player Session, so the world cannot tell the
difference; what the world sends it lands in a perception buffer the driver reads. Plugins that
run automated characters subclass it and attach it with ``api.sessions.attach``.
"""

from __future__ import annotations

import time
import uuid
from collections import deque

from sage.network.session import Session, SessionState


class NullProtocol:
    """Protocol stand-in: always connected; sends land in the perception buffer."""

    def __init__(self, perception: deque):
        self.is_connected = True
        self.peer_info = "virtual://headless"
        self._perception = perception

    async def send(self, message: str) -> None:
        for line in message.replace("\r", "").split("\n"):
            line = line.strip()
            # JSON client notices are UI plumbing, not world perception.
            if line and line != ">" and not line.startswith("{"):
                self._perception.append({"at": time.time(), "text": line})

    async def close(self) -> None:
        self.is_connected = False


class VirtualSession(Session):
    virtual = True

    def __init__(self, player_id: str, perception_size: int = 60, prefix: str = "virtual"):
        self.perception: deque = deque(maxlen=perception_size)
        super().__init__(f"{prefix}-{uuid.uuid4().hex[:8]}", NullProtocol(self.perception))
        self.player_id = player_id
        self.state = SessionState.PLAYING

    def recent_perceptions(self, n: int = 15) -> list[str]:
        return [p["text"] for p in list(self.perception)[-n:]]
