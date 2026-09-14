"""Moderation against real Postgres: bans, sign-in history (addresses only when on), retention,
erasure, mutes, the report queue and the registration lock."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from sage.core.config import ModerationConfig
from sage.services import moderation
from sage.state.models import Account, AccountLogin, AddressBan, PlayerReport
from sage.state.postgres import PostgresState
from tests.fakes import StubSession
from tests.live.conftest import open_redis

pytestmark = pytest.mark.live


def _server(live_config, db, redis, **rules):
    return SimpleNamespace(
        db=db,
        redis=redis,
        config=SimpleNamespace(moderation=ModerationConfig(**rules)),
        session_manager=SimpleNamespace(get_session_by_player=lambda name: None),
    )


async def _account(db, username: str) -> int:
    async with db.session_factory() as session:
        await session.execute(delete(Account).where(Account.username == username))
        account = Account(username=username, password_hash="x")
        session.add(account)
        await session.commit()
        return account.id


def test_bans_cover_addresses_and_ranges_until_they_expire(live_config, migrated_database):
    async def go():
        db = PostgresState(live_config.database)
        try:
            async with open_redis(live_config) as redis:
                server = _server(live_config, db, redis)
                async with db.session_factory() as session:
                    await session.execute(delete(AddressBan))
                    session.add(
                        AddressBan(network="198.51.100.0/24", reason="spam", created_by="t")
                    )
                    session.add(
                        AddressBan(
                            network="203.0.113.5/32",
                            reason="old",
                            created_by="t",
                            expires_at=datetime.utcnow() - timedelta(days=1),
                        )
                    )
                    await session.commit()
                assert (await moderation.active_ban(server, "198.51.100.77"))["reason"] == "spam"
                assert await moderation.active_ban(server, "198.51.101.1") is None
                assert await moderation.active_ban(server, "203.0.113.5") is None  # expired
                assert await moderation.active_ban(server, "not-an-address") is None
        finally:
            await db.close()

    asyncio.run(go())


def test_sign_in_history_keeps_addresses_only_while_recording_is_on(live_config, migrated_database):
    async def go():
        db = PostgresState(live_config.database)
        try:
            async with open_redis(live_config) as redis:
                account_id = await _account(db, "mod_history")
                off = _server(live_config, db, redis)
                on = _server(live_config, db, redis, record_login_addresses=True)
                await moderation.record_login(off, account_id, "password", "192.0.2.10")
                await moderation.record_login(on, account_id, "token", "192.0.2.11")
                history = await moderation.login_history(on, account_id=account_id)
                assert [(r["method"], r["address"]) for r in history["rows"]] == [
                    ("token", "192.0.2.11"),
                    ("password", None),
                ]
                assert (await moderation.login_history(on, address="192.0.2.0/24"))["total"] >= 1
                assert (await moderation.login_history(on, address="192.0.2.11"))["rows"][0][
                    "account"
                ] == "mod_history"

                # Older than the retention period: removed by the purge.
                async with db.session_factory() as session:
                    session.add(
                        AccountLogin(
                            account_id=account_id,
                            method="password",
                            address="192.0.2.12",
                            at=datetime.utcnow() - timedelta(days=40),
                        )
                    )
                    await session.commit()
                assert await moderation.purge_history(on) >= 1
                assert (await moderation.login_history(on, account_id=account_id))["total"] == 2

                assert await moderation.erase_addresses(on, account_id) == 1
                rows = (await moderation.login_history(on, account_id=account_id))["rows"]
                assert [r["address"] for r in rows] == [None, None]
        finally:
            await db.close()

    asyncio.run(go())


def test_mutes_and_reports(live_config, migrated_database):
    async def go():
        db = PostgresState(live_config.database)
        try:
            async with open_redis(live_config) as redis:
                account_id = await _account(db, "mod_mute")
                server = _server(live_config, db, redis, report_cooldown_seconds=60)
                muted = await moderation.set_mute(server, account_id, 30, "spamming say")
                assert muted["muted_until"] is not None
                async with db.session_factory() as session:
                    account = await session.get(Account, account_id)
                    assert account.mute_reason == "spamming say"
                await moderation.set_mute(server, account_id, None)
                async with db.session_factory() as session:
                    account = await session.get(Account, account_id)
                    assert (account.muted_until, account.mute_reason) == (None, None)
                with pytest.raises(LookupError):
                    await moderation.set_mute(server, 999_999, 5)

                session = StubSession("Mod Reporter")
                session.account_id = account_id
                await redis.set_player_location("Mod Reporter", "town:market")
                moderation._last_report.pop("Mod Reporter", None)
                assert await moderation.file_report(server, session, "   ") == (
                    "report.usage",
                    None,
                )
                key, report_id = await moderation.file_report(
                    server, session, "The bridge exit loops"
                )
                assert key == "report.thanks" and report_id
                assert (await moderation.file_report(server, session, "again"))[
                    0
                ] == "report.too_soon"

                queue = await moderation.reports(server, status="open")
                mine = next(r for r in queue["rows"] if r["id"] == report_id)
                assert (mine["character"], mine["room_id"]) == ("Mod Reporter", "town:market")
                done = await moderation.update_report(
                    server, report_id, status="fixed", note="exit fixed", by="gm_ann"
                )
                assert done["status"] == "fixed"
                with pytest.raises(ValueError):
                    await moderation.update_report(
                        server, report_id, status="lost", note=None, by="x"
                    )
                async with db.session_factory() as db_session:
                    row = await db_session.get(PlayerReport, report_id)
                    assert (row.handled_by, row.staff_note) == ("gm_ann", "exit fixed")
                    await db_session.execute(
                        delete(PlayerReport).where(PlayerReport.id == report_id)
                    )
                    await db_session.commit()
        finally:
            await db.close()

    asyncio.run(go())


def test_registration_lock_and_address_bans_refuse_sign_up_and_sign_in(
    live_config, migrated_database
):
    from sage.services.player_service import PlayerService

    async def go():
        db = PostgresState(live_config.database)
        try:
            async with open_redis(live_config) as redis:
                server = _server(live_config, db, redis, registration_open=False)
                server.config.comfyui = SimpleNamespace(starting_ai_credits=0)
                service = PlayerService(server)
                closed = await service.register("mod_newcomer", "long-enough-password")
                assert closed == {"ok": False, "error": "registration_closed"}
                async with db.session_factory() as session:
                    found = await session.execute(
                        select(Account).where(Account.username == "mod_newcomer")
                    )
                    assert found.scalar_one_or_none() is None

                server.config.moderation = ModerationConfig()
                async with db.session_factory() as session:
                    await session.execute(delete(AddressBan))
                    session.add(AddressBan(network="198.51.100.0/24", created_by="t"))
                    await session.commit()
                banned = await service.register(
                    "mod_newcomer", "long-enough-password", "198.51.100.9"
                )
                assert banned == {"ok": False, "error": "address_banned"}
                assert (await service.login("anyone", "x", "198.51.100.9"))[
                    "error"
                ] == "address_banned"
        finally:
            await db.close()

    asyncio.run(go())
