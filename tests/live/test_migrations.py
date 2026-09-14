"""Migrations against a real Postgres: head, full round-trip, and model drift."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

import fablestar.state.models  # noqa: F401  (registers tables on Base.metadata)
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fablestar.state.postgres import Base, PostgresState

pytestmark = pytest.mark.live

EXPECTED_TABLES = {
    "accounts",
    "characters",
    "admin_staff",
    "agent_state",
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
