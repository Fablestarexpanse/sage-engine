"""The admin console's live log feed (/ws/logs) receives server warnings and errors."""

from __future__ import annotations

import asyncio
import logging

from sage.admin.nexus import AdminLogBroadcastHandler


class _Nexus:
    def __init__(self):
        self._active_sockets = [object()]
        self.sent: list[tuple[str, str]] = []

    async def broadcast_log(self, message: str, level: str = "info"):
        self.sent.append((level, message))


def test_warnings_and_errors_reach_connected_consoles_and_info_does_not():
    async def scenario():
        nexus = _Nexus()
        handler = AdminLogBroadcastHandler(nexus, asyncio.get_running_loop())
        log = logging.getLogger("sage.world.loader")
        log.addHandler(handler)
        try:
            log.info("room loaded")
            log.warning("slow tick")
            log.error("Error loading room start:commons: bad yaml\n  in file, line 6")
            logging.getLogger("sage.admin.nexus").warning("socket died")  # its own module: skipped
            for _ in range(5):
                await asyncio.sleep(0)
        finally:
            log.removeHandler(handler)
        return nexus.sent

    sent = asyncio.run(scenario())
    assert sent == [
        ("warning", "sage.world.loader: slow tick"),
        ("error", "sage.world.loader: Error loading room start:commons: bad yaml"),
    ]


def test_nothing_is_scheduled_without_a_console():
    async def scenario():
        nexus = _Nexus()
        nexus._active_sockets = []
        handler = AdminLogBroadcastHandler(nexus, asyncio.get_running_loop())
        record = logging.LogRecord("sage.x", logging.ERROR, __file__, 1, "boom", None, None)
        handler.emit(record)
        await asyncio.sleep(0)
        return nexus.sent

    assert asyncio.run(scenario()) == []
