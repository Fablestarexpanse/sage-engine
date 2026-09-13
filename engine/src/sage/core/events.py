"""EventBus and engine domain events (docs/sage/PHASE1_CONTRACTS.md D.B, catalog #5).

Events are fan-out notifications with no return value. Subscribers run in subscription order
(engine first, then plugins in load order) and are awaited. A failing subscriber is logged with
its owner and never breaks the publisher or the other subscribers.

Events that subscribers may enrich carry mutable fields (``stats``, ``messages``): a subscriber
reacting to a kill can update the killer's stats blob and add lines the caller sends.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Event")


@dataclass
class Event:
    """Base class for all engine events."""

    timestamp: datetime = field(default_factory=datetime.now, kw_only=True)


@dataclass
class CommandExecuted(Event):
    player_id: str | None
    verb: str
    args: list[str]


@dataclass
class RoomEntered(Event):
    player_id: str
    room_id: str
    from_room_id: str | None
    direction: str | None = None


@dataclass
class EntityKilled(Event):
    killer_id: str
    entity_id: str
    template: str
    room_id: str
    faction: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


@dataclass
class PlayerDied(Event):
    player_id: str
    room_id: str | None
    cause: str
    is_agent: bool = False
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class CountersChanged(Event):
    """Counters on a character's stats blob just moved; subscribers may add player lines."""

    player_id: str
    counters: list[str]
    stats: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


@dataclass
class SessionStarted(Event):
    player_id: str


@dataclass
class SessionEnded(Event):
    player_id: str


@dataclass
class _Subscription:
    handler: Callable[[Any], Any]
    owner: str


class EventBus:
    """Exact-type publish/subscribe; subclasses of an event type are separate channels."""

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[_Subscription]] = {}

    def subscribe(
        self, event_type: type[T], handler: Callable[[T], Any], owner: str = "sage"
    ) -> None:
        self._subscribers.setdefault(event_type, []).append(_Subscription(handler, owner))

    def unsubscribe_owner(self, owner: str) -> None:
        for event_type, subs in self._subscribers.items():
            self._subscribers[event_type] = [s for s in subs if s.owner != owner]

    def subscribers(self, event_type: type[Event]) -> list[str]:
        """Owners subscribed to event_type, in call order."""
        return [s.owner for s in self._subscribers.get(event_type, [])]

    async def publish(self, event: Event) -> None:
        for sub in list(self._subscribers.get(type(event), [])):
            try:
                result = sub.handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception(
                    "Event subscriber %s (owner %s) failed on %s",
                    getattr(sub.handler, "__qualname__", sub.handler),
                    sub.owner,
                    type(event).__name__,
                )


async def emit(server: Any, event: Event) -> None:
    """Publish on the server's bus when it has one (test fakes may not)."""
    bus = getattr(server, "events", None)
    if bus is not None:
        await bus.publish(event)
