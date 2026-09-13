"""AgentSession — a player session with no socket; output becomes perception."""

import time
import uuid
from collections import deque

from sage.network.session import Session, SessionState


class NullProtocol:
    """Protocol stand-in: always connected, sends land in the agent's perception log."""

    def __init__(self, perception: deque):
        self.is_connected = True
        self.peer_info = "agent://headless"
        self._perception = perception

    async def send(self, message: str):
        for line in message.replace("\r", "").split("\n"):
            line = line.strip()
            # JSON client notices are UI plumbing, not world perception.
            if line and line != ">" and not line.startswith("{"):
                self._perception.append({"at": time.time(), "text": line})

    async def close(self):
        self.is_connected = False


class AgentSession(Session):
    """Same contract as a player Session; the world cannot tell the difference."""

    virtual = True  # no socket: client-only JSON notices, rate limits and UI snapshots are skipped

    def __init__(self, agent_id: str, name: str, perception_size: int = 60):
        self.perception: deque = deque(maxlen=perception_size)
        super().__init__(f"agent-{uuid.uuid4().hex[:8]}", NullProtocol(self.perception))
        self.agent_id = agent_id
        self.player_id = name
        self.state = SessionState.PLAYING

    def recent_perceptions(self, n: int = 15) -> list[str]:
        return [p["text"] for p in list(self.perception)[-n:]]
