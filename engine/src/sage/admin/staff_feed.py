"""What is happening in the world right now, for staff: sign-ins, deaths, kills, new characters,
reports and restart notices, newest last.

Entries come from engine events on the bus (so plugin-published events of the same types appear
too) plus a few direct calls (reports, restarts). The feed is kept in memory: the newest
``MAX_ENTRIES`` since the server started. It is a live view, not a record; the audit log keeps
staff actions.
"""

from __future__ import annotations

import itertools
from collections import deque
from datetime import UTC, datetime
from typing import Any

MAX_ENTRIES = 1000
KINDS = ("signin", "signout", "death", "kill", "character", "report", "server")


def _room_href(room_id: str | None) -> str | None:
    if not room_id or ":" not in room_id:
        return None
    zone, slug = room_id.split(":", 1)
    return f"#/content/rooms/{zone}/{slug}"


class StaffFeed:
    def __init__(self) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)
        self._ids = itertools.count(1)

    def add(
        self,
        kind: str,
        text: str,
        *,
        player: str | None = None,
        room_id: str | None = None,
        href: str | None = None,
        agent: bool = False,
    ) -> dict[str, Any]:
        entry = {
            "id": next(self._ids),
            "at": datetime.now(UTC).isoformat(),
            "kind": kind,
            "text": text,
            "player": player,
            "room_id": room_id,
            "href": href or _room_href(room_id),
            "agent": agent,
        }
        self._entries.append(entry)
        return entry

    def since(
        self, after: int = 0, kinds: set[str] | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        rows = [e for e in self._entries if e["id"] > after and (not kinds or e["kind"] in kinds)]
        return rows[-limit:]

    def attach(self, server: Any) -> None:
        """Subscribe to the engine events the feed shows."""
        from sage.core.events import (
            CharacterCreated,
            EntityKilled,
            PlayerDied,
            SessionEnded,
            SessionStarted,
        )

        bus = server.events

        def is_agent(name: str) -> bool:
            session = server.session_manager.get_session_by_player(name)
            return bool(getattr(session, "virtual", False))

        async def signed_in(event: SessionStarted) -> None:
            room = await server.redis.get_player_location(event.player_id)
            self.add(
                "signin",
                f"{event.player_id} entered the world",
                player=event.player_id,
                room_id=room,
                agent=is_agent(event.player_id),
            )

        async def signed_out(event: SessionEnded) -> None:
            self.add("signout", f"{event.player_id} left", player=event.player_id)

        def died(event: PlayerDied) -> None:
            self.add(
                "death",
                f"{event.player_id} died ({event.cause})",
                player=event.player_id,
                room_id=event.room_id,
                agent=event.virtual,
            )

        def killed(event: EntityKilled) -> None:
            self.add(
                "kill",
                f"{event.killer_id} killed {event.template}",
                player=event.killer_id,
                room_id=event.room_id,
                agent=is_agent(event.killer_id),
            )

        def created(event: CharacterCreated) -> None:
            self.add(
                "character",
                f"New character {event.player_id} on account {event.account}",
                player=event.player_id,
                href=f"#/characters/{event.character_id}",
            )

        bus.subscribe(SessionStarted, signed_in, owner="staff_feed")
        bus.subscribe(SessionEnded, signed_out, owner="staff_feed")
        bus.subscribe(PlayerDied, died, owner="staff_feed")
        bus.subscribe(EntityKilled, killed, owner="staff_feed")
        bus.subscribe(CharacterCreated, created, owner="staff_feed")
