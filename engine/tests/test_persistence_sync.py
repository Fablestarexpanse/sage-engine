"""PersistenceManager.sync_character — the Redis→Postgres durability write.

Uses FakeRedis plus a fake async session that answers the Character select,
verifying the row actually receives location/stats/inventory and that DB
failures are swallowed (game loop must survive them).
"""

import asyncio
from types import SimpleNamespace

from sage.state.models import Character
from sage.state.persistence import PersistenceManager
from tests.fakes import FakeRedis, fake_wallet


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self, row, fail=False):
        self._row = row
        self._fail = fail
        self.began = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return self  # reused as the begin() context manager

    async def execute(self, stmt):
        if self._fail:
            raise RuntimeError("db down")
        self.began = True
        return _FakeResult(self._row)


def _server(row, fail=False):
    srv = SimpleNamespace()
    srv.redis = FakeRedis()
    srv.wallet = fake_wallet()
    srv.db = SimpleNamespace(session_factory=lambda: _FakeSession(row, fail=fail))
    return srv


def test_sync_character_writes_live_state_to_row():
    asyncio.run(_check_writes_live_state())


async def _check_writes_live_state():
    row = Character()
    row.name = "hero"
    row.room_id = "old_zone:old_room"
    row.stats = {"hp": 1}
    row.inventory = []

    srv = _server(row)
    await srv.redis.set_player_location("hero", "new_zone:bridge")
    await srv.redis.set_player_stats("hero", {"hp": 17, "credits": 5})
    await srv.redis.set_player_inventory("hero", ["item_1"])

    await PersistenceManager(srv).sync_character("hero")

    assert row.room_id == "new_zone:bridge"
    assert row.stats == {"hp": 17, "credits": 5}
    assert row.inventory == ["item_1"]
    assert row.updated_at is not None


def test_sync_character_missing_row_is_noop():
    asyncio.run(_check_missing_row_noop())


async def _check_missing_row_noop():
    srv = _server(None)
    await srv.redis.set_player_location("ghost", "zone:room")
    # must not raise even though no Character row matches
    await PersistenceManager(srv).sync_character("ghost")


def test_sync_character_swallows_db_failure():
    asyncio.run(_check_swallows_db_failure())


async def _check_swallows_db_failure():
    row = Character()
    row.name = "hero"
    srv = _server(row, fail=True)
    await srv.redis.set_player_location("hero", "zone:room")
    # documented contract: durability write failures are logged, never raised
    await PersistenceManager(srv).sync_character("hero")
