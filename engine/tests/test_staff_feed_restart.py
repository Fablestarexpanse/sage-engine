"""The staff feed shows engine events; the scheduled restart warns, closes sign-ins, saves, stops."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sage.admin import restart as restart_mod
from sage.admin.restart import RestartScheduler
from sage.admin.staff_feed import MAX_ENTRIES, StaffFeed
from sage.core.events import CharacterCreated, EventBus, PlayerDied, SessionStarted
from tests.fakes import FakeRedis


def test_feed_keeps_the_newest_entries_and_filters_by_kind():
    feed = StaffFeed()
    for n in range(MAX_ENTRIES + 5):
        feed.add("kill" if n % 2 else "death", f"entry {n}", room_id="town:inn")
    entries = feed.since()
    assert len(entries) == 200  # default page
    assert entries[-1]["text"] == f"entry {MAX_ENTRIES + 4}"
    assert entries[-1]["href"] == "#/content/rooms/town/inn"
    newest = entries[-1]["id"]
    assert feed.since(after=newest) == []
    assert {e["kind"] for e in feed.since(kinds={"death"}, limit=1000)} == {"death"}
    assert len(feed.since(limit=5000)) == MAX_ENTRIES


def test_feed_turns_engine_events_into_entries():
    agent = SimpleNamespace(virtual=True)
    server = SimpleNamespace(
        events=EventBus(),
        redis=FakeRedis(),
        session_manager=SimpleNamespace(
            get_session_by_player=lambda name: agent if name == "Sela" else None
        ),
    )
    feed = StaffFeed()
    feed.attach(server)

    async def run():
        await server.redis.set_player_location("Ann", "town:gate")
        await server.events.publish(SessionStarted(player_id="Ann"))
        await server.events.publish(
            PlayerDied(player_id="Sela", room_id="town:inn", cause="rat", virtual=True)
        )
        await server.events.publish(CharacterCreated(player_id="Bo", character_id=9, account="bo"))

    asyncio.run(run())
    entries = feed.since()
    assert [(e["kind"], e["player"], e["agent"]) for e in entries] == [
        ("signin", "Ann", False),
        ("death", "Sela", True),
        ("character", "Bo", False),
    ]
    assert entries[0]["room_id"] == "town:gate"
    assert entries[2]["href"] == "#/characters/9"


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture()
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(restart_mod.time, "monotonic", c)
    return c


def _server():
    said = []
    stopped = []

    async def broadcast(message, exclude=None):
        said.append(message)

    async def flush_all():
        said.append("<flushed>")

    server = SimpleNamespace(
        session_manager=SimpleNamespace(broadcast=broadcast, sessions={}),
        persistence=SimpleNamespace(flush_all=flush_all),
        request_stop=lambda: stopped.append(True),
        staff_feed=StaffFeed(),
    )
    return server, said, stopped


def test_restart_counts_down_closes_sign_ins_saves_and_stops(clock):
    server, said, stopped = _server()
    scheduler = RestartScheduler(server)

    async def run():
        with pytest.raises(ValueError):
            await scheduler.schedule(5, "", "gm")
        await scheduler.schedule(125, "patch day", "gm")
        assert len(said) == 1 and "patch day" in said[0] and "2 minutes" in said[0]
        assert not scheduler.signins_closed()
        for left in (120, 90, 60, 45, 30, 11, 10, 1):
            clock.now = 1000.0 + 125 - left
            await scheduler.on_tick(0)
        assert scheduler.signins_closed()
        warnings = [s for s in said if "restarts in" in s]
        assert len(warnings) == 5  # at scheduling, then the 120, 60, 30 and 10 second marks
        clock.now = 1000.0 + 125
        await scheduler.on_tick(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run())
    assert "<flushed>" in said and stopped == [True]
    assert [e["kind"] for e in server.staff_feed.since()] == ["server", "server"]


def test_a_restart_can_be_cancelled(clock):
    server, said, stopped = _server()
    scheduler = RestartScheduler(server)

    async def run():
        assert await scheduler.cancel("gm") is False
        await scheduler.schedule(600, "", "gm")
        assert await scheduler.cancel("gm") is True
        clock.now += 700
        await scheduler.on_tick(0)

    asyncio.run(run())
    assert stopped == [] and scheduler.status()["scheduled"] is False
    assert "cancelled" in said[-1]
