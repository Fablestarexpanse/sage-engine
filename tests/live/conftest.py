"""Live-tier fixtures: a throwaway Postgres database and Redis db 15 (STANDARDS 3.5).

Nothing here touches the dev database: every session creates ``sage_live_<hex>``, migrates
it, and drops it at the end. Alembic's env.py calls ``load_config()`` itself and runs its own
event loop, so the database name reaches it through environment overrides and alembic
commands are only ever invoked from synchronous code.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest

from alembic.config import Config as AlembicConfig
from fablestar.core.config import Config, DatabaseConfig, load_config
from fablestar.state.redis_client import RedisState

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_REDIS_DB = 15


def _password(db: DatabaseConfig) -> str | None:
    pw = db.password
    return pw.get_secret_value() if hasattr(pw, "get_secret_value") else pw


async def _admin_execute(db: DatabaseConfig, *statements: str) -> None:
    conn = await asyncpg.connect(
        host=db.host, port=db.port, user=db.user, password=_password(db), database="postgres"
    )
    try:
        for sql in statements:
            await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def live_db_name() -> str:
    return f"sage_live_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def live_config(live_db_name: str) -> Iterator[Config]:
    overrides = {
        "FABLESTAR_DATABASE__DATABASE": live_db_name,
        "FABLESTAR_REDIS__DB": str(LIVE_REDIS_DB),
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        yield load_config(str(REPO_ROOT / "config"))
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def live_database(live_config: Config) -> Iterator[str]:
    db = live_config.database
    name = db.database
    assert name.startswith("sage_live_"), f"refusing to manage non-throwaway database {name!r}"
    asyncio.run(_admin_execute(db, f'CREATE DATABASE "{name}"'))
    try:
        yield name
    finally:
        asyncio.run(
            _admin_execute(
                db,
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
                f'DROP DATABASE IF EXISTS "{name}"',
            )
        )


@pytest.fixture(scope="session")
def alembic_cfg(live_database: str) -> AlembicConfig:
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def migrated_database(alembic_cfg: AlembicConfig, live_database: str) -> str:
    from alembic import command

    command.upgrade(alembic_cfg, "head")
    return live_database


@asynccontextmanager
async def open_redis(config: Config) -> AsyncIterator[RedisState]:
    """Connected RedisState on the live db, flushed before and after use."""
    assert config.redis.db == LIVE_REDIS_DB, "live Redis must use its own db index"
    state = RedisState(config.redis)
    await state.connect()
    await state.client.flushdb()
    try:
        yield state
    finally:
        await state.client.flushdb()
        await state.disconnect()
