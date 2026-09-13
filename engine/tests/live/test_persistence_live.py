"""Redis state and the Redis->Postgres durability write against real services."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from sage.state.models import Account, Character
from sage.state.persistence import PersistenceManager
from sage.state.postgres import PostgresState
from tests.fakes import fake_wallet
from tests.live.conftest import open_redis

pytestmark = pytest.mark.live


def test_redis_state_roundtrip(live_config):
    async def go():
        async with open_redis(live_config) as redis:
            await redis.set_player_location("live_hero", "probe:room")
            await redis.set_player_stats("live_hero", {"hp": 9})
            await redis.set_player_inventory("live_hero", [{"id": "i1", "template": "rope"}])
            await redis.add_player_to_room("live_hero", "probe:room")
            assert await redis.get_player_location("live_hero") == "probe:room"
            assert (await redis.get_player_stats("live_hero"))["hp"] == 9
            assert len(await redis.get_player_inventory("live_hero")) == 1
            assert "live_hero" in await redis.get_room_players("probe:room")
            await redis.remove_player_from_room("live_hero", "probe:room")
            assert "live_hero" not in await redis.get_room_players("probe:room")

    asyncio.run(go())


def test_sync_character_writes_real_row(live_config, migrated_database):
    async def go():
        db = PostgresState(live_config.database)
        try:
            async with db.session_factory() as session, session.begin():
                account = Account(username="live_account", password_hash="x")
                session.add(account)
                await session.flush()
                session.add(
                    Character(account_id=account.id, name="live_hero", room_id="probe:start")
                )

            async with open_redis(live_config) as redis:
                await redis.set_player_location("live_hero", "probe:end")
                await redis.set_player_stats("live_hero", {"hp": 7, "coin": 42})
                await redis.set_player_inventory("live_hero", [{"id": "i1", "template": "rope"}])
                server = SimpleNamespace(
                    redis=redis, db=db, agent_manager=None, wallet=fake_wallet("coin")
                )
                await PersistenceManager(server).sync_character("live_hero")

            async with db.session_factory() as session:
                row = (
                    await session.execute(select(Character).where(Character.name == "live_hero"))
                ).scalar_one()
            assert row.room_id == "probe:end"
            assert row.stats["hp"] == 7
            assert row.digi_balance == 42
            assert len(row.inventory) == 1
        finally:
            await db.close()

    asyncio.run(go())
