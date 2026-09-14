"""WebSocketProtocol — wraps a FastAPI WebSocket for player sessions."""

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketProtocol:
    """WebSocket transport for a player session."""

    def __init__(self, websocket: WebSocket):
        self._websocket = websocket
        self._is_connected = True
        self._peer = (
            f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "web-client"
        )
        # The connecting address (moderation: bans and, when the operator records them, history).
        self.address = websocket.client.host if websocket.client else None
        self._incoming_queue: asyncio.Queue[str] = asyncio.Queue()

    async def send(self, message: str) -> None:
        """Send text to the web client."""
        if not self._is_connected:
            return

        try:
            # We send as a simple string; the frontend will handle terminal rendering
            await self._websocket.send_text(message)
        except Exception as e:
            logger.debug("websocket send failed for %s: %s", self._peer, e)
            self._is_connected = False

    async def receive(self) -> str | None:
        """Receive a line of text from the web client."""
        if not self._is_connected:
            return None

        try:
            # FastAPI's receive_text blocks, so we use the queue if we want
            # to handle heartbeats or other messages elsewhere,
            # but for a simple MUD loop, we can just return it.
            data = await self._websocket.receive_text()
            return data.strip()
        except Exception as e:
            logger.debug("websocket receive ended for %s: %s", self._peer, e)
            self._is_connected = False
            return None

    async def close(self) -> None:
        """Close the websocket."""
        self._is_connected = False
        try:
            await self._websocket.close()
        except Exception as e:
            logger.debug("websocket close for %s: %s", self._peer, e)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def peer_info(self) -> str:
        return self._peer
