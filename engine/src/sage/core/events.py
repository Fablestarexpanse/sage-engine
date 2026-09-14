"""Async EventBus — pub/sub for game events (tick, session connect/disconnect, etc.)."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

T = TypeVar("T", bound="Event")


@dataclass
class Event:
    """Base class for all engine events."""

    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """
    A lightweight, asynchronous Pub/Sub event bus.
    Allows decoupling of engine components.
    """

    def __init__(self) -> None:
        self._subscribers: dict[
            type[Event], list[Callable[[Any], asyncio.Future[None] | None]]
        ] = {}
        self._global_subscribers: list[Callable[[Event], asyncio.Future[None] | None]] = []

    def subscribe(self, event_type: type[T], handler: Callable[[T], Any]) -> None:
        """Subscribe a handler to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[Event], Any]) -> None:
        """Subscribe a handler to all events passing through the bus."""
        self._global_subscribers.append(handler)

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all interested subscribers.
        Handlers are executed concurrently, but we wait for all of them to complete.
        """
        handlers = self._subscribers.get(type(event), [])
        tasks = []

        # Notify specific subscribers
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                tasks.append(asyncio.create_task(handler(event)))
            else:
                handler(event)

        # Notify global subscribers
        for handler in self._global_subscribers:
            if asyncio.iscoroutinefunction(handler):
                tasks.append(asyncio.create_task(handler(event)))
            else:
                handler(event)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
