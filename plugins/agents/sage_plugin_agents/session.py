"""AgentSession — a virtual session carrying the persona it drives."""

from sage.api import VirtualSession


class AgentSession(VirtualSession):
    """Same contract as a player Session; the world cannot tell the difference."""

    def __init__(self, agent_id: str, name: str, perception_size: int = 60):
        super().__init__(name, perception_size, prefix="agent")
        self.agent_id = agent_id
