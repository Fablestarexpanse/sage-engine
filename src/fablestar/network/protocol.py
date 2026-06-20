"""Abstract Protocol transport — concrete implementation is WebSocketProtocol."""

from abc import ABC, abstractmethod


class Protocol(ABC):
    """Abstract transport for a player session (WebSocket implementation today)."""

    @abstractmethod
    async def send(self, message: str) -> None:
        """Send a message to the client."""
        pass

    @abstractmethod
    async def receive(self) -> str | None:
        """Receive a message from the client."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the connection is still active."""
        pass

    @property
    @abstractmethod
    def peer_info(self) -> str:
        """Return information about the connected peer (e.g. IP address)."""
        pass
