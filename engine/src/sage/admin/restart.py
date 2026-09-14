"""Scheduled restart: warn players on a countdown, stop new sign-ins near the end, save, and stop.

The engine stops itself; whether it starts again is up to what runs it (Docker's restart policy,
systemd, a service manager). Warnings go out at the ``WARN_AT`` marks still ahead when the restart
is scheduled. In the last ``CLOSE_SIGNINS_AT`` seconds new play connections are refused.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

WARN_AT = (1800, 900, 600, 300, 120, 60, 30, 10)
CLOSE_SIGNINS_AT = 60
MIN_SECONDS = 10
MAX_SECONDS = 24 * 3600


class RestartScheduler:
    def __init__(self, server: Any) -> None:
        self.server = server
        self.due: float | None = None  # time.monotonic() deadline
        self.reason = ""
        self.by = ""
        self.scheduled_at = ""
        self._warned: set[int] = set()
        self._running = False

    def status(self) -> dict[str, Any]:
        left = self.seconds_left()
        return {
            "scheduled": left is not None,
            "seconds_left": left,
            "reason": self.reason if left is not None else "",
            "by": self.by if left is not None else "",
            "scheduled_at": self.scheduled_at if left is not None else "",
            "signins_closed": self.signins_closed(),
        }

    def seconds_left(self) -> int | None:
        if self.due is None:
            return None
        return max(0, round(self.due - time.monotonic()))

    def signins_closed(self) -> bool:
        left = self.seconds_left()
        return left is not None and left <= CLOSE_SIGNINS_AT

    async def schedule(self, seconds: int, reason: str, by: str) -> dict[str, Any]:
        from datetime import UTC, datetime

        if not MIN_SECONDS <= int(seconds) <= MAX_SECONDS:
            raise ValueError(f"seconds must be between {MIN_SECONDS} and {MAX_SECONDS}")
        self.due = time.monotonic() + int(seconds)
        self.reason = (reason or "").strip()[:200]
        self.by = by
        self.scheduled_at = datetime.now(UTC).isoformat()
        # Marks already passed are not announced; the first warning goes out now.
        self._warned = {mark for mark in WARN_AT if mark >= int(seconds)}
        await self._announce(int(seconds))
        self._feed(f"Restart scheduled in {_duration(int(seconds))} by {by}")
        return self.status()

    async def cancel(self, by: str) -> bool:
        if self.due is None or self._running:
            return False
        self.due = None
        self._warned = set()
        await self.server.session_manager.broadcast(_t("restart.cancelled"))
        self._feed(f"Restart cancelled by {by}")
        return True

    async def on_tick(self, _tick: int) -> None:
        left = self.seconds_left()
        if left is None or self._running:
            return
        if left <= 0:
            self._running = True
            asyncio.get_running_loop().create_task(self._restart_now())
            return
        for mark in WARN_AT:
            if left <= mark and mark not in self._warned:
                self._warned.add(mark)
                await self._announce(left)
                break

    async def _announce(self, seconds: int) -> None:
        text = _t("restart.warning", when=_duration(seconds))
        if self.reason:
            text = f"{text} {_t('restart.reason', reason=self.reason)}"
        await self.server.session_manager.broadcast(text)

    async def _restart_now(self) -> None:
        server = self.server
        logger.warning("Scheduled restart: saving characters and stopping")
        self._feed("Restarting now")
        try:
            await server.session_manager.broadcast(_t("restart.now"))
            await server.persistence.flush_all()
        except Exception:
            logger.error("Scheduled restart: save before stopping failed", exc_info=True)
        for session in list(server.session_manager.sessions.values()):
            if getattr(session, "virtual", False):
                continue
            try:
                await session.end("restart", _t("restart.goodbye"))
            except Exception:
                pass
        server.request_stop()

    def _feed(self, text: str) -> None:
        feed = getattr(self.server, "staff_feed", None)
        if feed is not None:
            feed.add("server", text)


def _t(key: str, **values: Any) -> str:
    from sage import lexicon

    return lexicon.t(key, **values)


def _duration(seconds: int) -> str:
    from sage import lexicon

    if seconds >= 120:
        return lexicon.t("restart.minutes", n=round(seconds / 60))
    if seconds >= 60:
        return lexicon.t("restart.one_minute")
    return lexicon.t("restart.seconds", n=seconds)
