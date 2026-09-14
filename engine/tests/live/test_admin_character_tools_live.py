"""Admin character tools, account suspension and the audit log against real Postgres and Redis.

The tools must write a character's live Redis state as well as its Postgres row: the persistence
flush copies Redis over Postgres, so a Postgres-only edit of a character that has logged in is
undone within a minute. Each test ends with that flush and checks the edit survived.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest import mock

import pytest
from sqlalchemy import select

from sage.admin import audit, character_tools, player_accounts
from sage.core.resolvers import Resolvers
from sage.services._shared import resolve_play_account
from sage.services.play_tokens import issue_play_token
from sage.state.models import Account, Character
from sage.state.persistence import PersistenceManager
from sage.state.postgres import PostgresState
from sage.world.loader import ContentLoader
from sage.world.package import load_world_package
from sage.world.slots import define_engine_slots
from sage.world.wallet import Wallet
from tests.fakes import ROOT
from tests.live.conftest import open_redis

pytestmark = pytest.mark.live

WORLD = load_world_package(ROOT / "worlds" / "rivermoot")
NAME = "Tool Tester"


def _server(live_config, db, redis):
    resolvers = Resolvers()
    define_engine_slots(resolvers, WORLD)
    return SimpleNamespace(
        db=db,
        redis=redis,
        world=WORLD,
        wallet=Wallet(WORLD),
        resolvers=resolvers,
        content_loader=ContentLoader(WORLD.content_dir),
        session_manager=SimpleNamespace(get_session_by_player=lambda name: None, sessions={}),
        config=SimpleNamespace(
            server=SimpleNamespace(
                admin_auth_required=True,
                admin_jwt_secret="live-test-secret-0123456789abcdef0123456789",
            )
        ),
        notify_play_clients_staff_audit=lambda *a, **k: asyncio.sleep(0),
    )


async def _character(db, redis, *, logged_in: bool) -> tuple[int, int]:
    async with db.session_factory() as session, session.begin():
        found = (
            await session.execute(select(Character).where(Character.name == NAME))
        ).scalar_one_or_none()
        if found is not None:
            await session.delete(found)
            await session.flush()
        account = (
            await session.execute(select(Account).where(Account.username == "tool_tester"))
        ).scalar_one_or_none()
        if account is None:
            account = Account(username="tool_tester", password_hash="x")
            session.add(account)
            await session.flush()
        account.suspended_at = None
        char = Character(
            account_id=account.id,
            name=NAME,
            room_id="town:bridge",
            stats={"hp": 12, "silver": 5},
            inventory=[],
        )
        session.add(char)
        await session.flush()
        ids = (char.id, account.id)
    if logged_in:  # what a login leaves in Redis, and keeps after logout
        await redis.set_player_location(NAME, "town:bridge")
        await redis.set_player_stats(NAME, {"hp": 12, "silver": 5})
        await redis.set_player_inventory(NAME, [])
    return ids


async def _flushed_row(server) -> Character:
    await PersistenceManager(server).sync_character(NAME)
    async with server.db.session_factory() as session:
        return (await session.execute(select(Character).where(Character.name == NAME))).scalar_one()


def test_tools_write_live_state_so_the_flush_keeps_the_change(live_config, migrated_database):
    async def go():
        db = PostgresState(live_config.database)
        try:
            async with open_redis(live_config) as redis:
                server = _server(live_config, db, redis)
                char_id, _ = await _character(db, redis, logged_in=True)

                moved = await character_tools.move(server, char_id, "town:market")
                assert moved["room_id"] == "town:market"
                assert await redis.get_player_location(NAME) == "town:market"

                money = await character_tools.set_balance(server, char_id, "silver", 99)
                assert (money["before"], money["after"]) == (5, 99)

                given = await character_tools.give_item(server, char_id, "bread_loaf")
                item_id = given["item"]["id"]
                assert [i["template"] for i in await redis.get_player_inventory(NAME)] == [
                    "bread_loaf"
                ]

                row = await _flushed_row(server)
                assert row.room_id == "town:market"
                assert row.stats["silver"] == 99
                assert [i["id"] for i in row.inventory] == [item_id]

                await character_tools.remove_item(server, char_id, item_id)
                assert (await _flushed_row(server)).inventory == []

                with pytest.raises(character_tools.CharacterToolError):
                    await character_tools.move(server, char_id, "town:nowhere")
                with pytest.raises(character_tools.CharacterToolError):
                    await character_tools.set_balance(server, char_id, "gold", 1)
                with pytest.raises(character_tools.CharacterToolError):
                    await character_tools.give_item(server, char_id, "no_such_item")

                detail = await character_tools.detail(server, char_id)
                assert detail["live_state"] is True and detail["room_id"] == "town:market"
                assert detail["currencies"][0]["key"] == "silver"
                assert [c["name"] for c in await character_tools.find(server, "tool")] == [NAME]
        finally:
            await db.close()

    asyncio.run(go())


def test_the_existing_character_edit_is_no_longer_undone_by_the_flush(
    live_config, migrated_database
):
    async def go():
        db = PostgresState(live_config.database)
        try:
            async with open_redis(live_config) as redis:
                server = _server(live_config, db, redis)
                char_id, account_id = await _character(db, redis, logged_in=True)
                await player_accounts.patch_character(
                    server,
                    account_id,
                    char_id,
                    {"room_id": "town:shrine", "stats": {"hp": 3, "silver": 40}},
                )
                row = await _flushed_row(server)
                assert row.room_id == "town:shrine"
                assert row.stats["silver"] == 40
        finally:
            await db.close()

    asyncio.run(go())


def test_suspension_blocks_play_tokens_until_lifted(live_config, migrated_database):
    async def go():
        db = PostgresState(live_config.database)
        try:
            async with open_redis(live_config) as redis:
                server = _server(live_config, db, redis)
                _, account_id = await _character(db, redis, logged_in=False)
                with mock.patch.dict("os.environ", {"SAGE_ADMIN_JWT_SECRET": ""}):
                    token = issue_play_token(server, account_id)

                    async def resolve():
                        async with db.session_factory() as session:
                            return await resolve_play_account(session, server, token=token)

                    assert (await resolve()).id == account_id
                    result = await character_tools.set_suspended(server, account_id, "spamming")
                    assert result["suspended"] is True
                    assert await resolve() is None
                    await character_tools.set_suspended(server, account_id, None)
                    assert (await resolve()).id == account_id
        finally:
            await db.close()

    asyncio.run(go())


def test_audit_rows_are_recorded_filtered_and_scrubbed(live_config, migrated_database):
    async def go():
        db = PostgresState(live_config.database)
        try:
            server = SimpleNamespace(db=db)
            ctx = SimpleNamespace(staff_id=7, username="auditor")
            await audit.record(server, ctx, "character.wallet", NAME, currency="silver", after=99)
            await audit.record(
                server,
                ctx,
                "PATCH /admin/staff/{staff_id}",
                "/admin/staff/3",
                body={"password": "hunter2!", "role": "gm"},
            )
            rows = await audit.recent(server, staff="auditor")
            assert rows[0]["action"] == "PATCH /admin/staff/{staff_id}"
            assert rows[0]["detail"]["body"] == {"password": "(changed)", "role": "gm"}
            wallet_rows = await audit.recent(server, action="character.")
            assert wallet_rows[0]["target"] == NAME and wallet_rows[0]["detail"]["after"] == 99
            older = await audit.recent(server, staff="auditor", before_id=rows[0]["id"])
            assert all(r["id"] < rows[0]["id"] for r in older)
        finally:
            await db.close()

    asyncio.run(go())
