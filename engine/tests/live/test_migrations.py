"""Migrations against a real Postgres: head, full round-trip, and model drift."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

import sage.state.models  # noqa: F401  (registers tables on Base.metadata)
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sage.state.postgres import Base, PostgresState

pytestmark = pytest.mark.live

EXPECTED_TABLES = {
    "accounts",
    "characters",
    "admin_staff",
    "retired_agent_state",
    "account_scene_images",
    "alembic_version",
}


def _run_sync(config, fn):
    """Run fn(sync_connection) on the live database and return its result."""

    async def go():
        engine = create_async_engine(PostgresState(config.database).url)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(fn)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _tables(config) -> set[str]:
    return set(_run_sync(config, lambda c: inspect(c).get_table_names()))


def test_upgrade_head_creates_expected_tables(live_config, migrated_database):
    assert EXPECTED_TABLES <= _tables(live_config)


def test_downgrade_base_then_upgrade_head_roundtrip(live_config, alembic_cfg, migrated_database):
    command.downgrade(alembic_cfg, "base")
    assert _tables(live_config) <= {"alembic_version"}, "downgrade base left tables behind"

    command.upgrade(alembic_cfg, "head")
    assert EXPECTED_TABLES <= _tables(live_config), "upgrade head did not restore the schema"


def test_models_match_migrations(live_config, migrated_database):
    def diff(conn):
        return compare_metadata(MigrationContext.configure(conn), Base.metadata)

    assert _run_sync(live_config, diff) == []


def test_wallet_balances_move_into_stats_and_back(live_config, alembic_cfg, migrated_database):
    """p9q0r1s2t3u4 copies the legacy wallet column into stats; downgrade copies it back."""
    from alembic.script import ScriptDirectory

    legacy = (
        ScriptDirectory.from_config(alembic_cfg).get_revision("p9q0r1s2t3u4").module.LEGACY_COLUMN
    )
    from sqlalchemy import text

    from sage.core.config import resolve_project_root
    from sage.world.package import select_world

    world = select_world(
        resolve_project_root() / live_config.server.worlds_dir, live_config.server.world
    )
    if not world.currencies:
        pytest.skip(f"world {world.id} declares no currencies")
    key = world.currencies[0].key

    def execute(sql, **params):
        def run(conn):
            result = conn.execute(text(sql), params)
            rows = result.all() if result.returns_rows else None
            conn.commit()
            return rows

        return _run_sync(live_config, run)

    command.downgrade(alembic_cfg, "o8p9q0r1s2t3")
    try:
        execute(
            "INSERT INTO accounts (username, password_hash, is_gm, created_at) "
            "VALUES ('wallet_mig', 'x', false, now())"
        )
        execute(
            f"INSERT INTO characters (account_id, name, room_id, {legacy}, pvp_enabled, "
            "reputation, stats, inventory, created_at, updated_at) "
            "SELECT id, 'wallet_hero', 'probe:start', 17, false, 0, '{\"hp\": 5}', '[]', now(), now() "
            "FROM accounts WHERE username = 'wallet_mig'"
        )
        command.upgrade(alembic_cfg, "head")
        [(stats,)] = execute("SELECT stats FROM characters WHERE name = 'wallet_hero'")
        assert stats == {"hp": 5, key: 17}

        execute(
            f"UPDATE characters SET stats = jsonb_set(stats, '{{{key}}}', '30') WHERE name = 'wallet_hero'"
        )
        command.downgrade(alembic_cfg, "o8p9q0r1s2t3")
        [(balance,)] = execute(f"SELECT {legacy} FROM characters WHERE name = 'wallet_hero'")
        assert balance == 30
    finally:
        command.upgrade(alembic_cfg, "head")
        execute("DELETE FROM characters WHERE name = 'wallet_hero'")
        execute("DELETE FROM accounts WHERE username = 'wallet_mig'")
