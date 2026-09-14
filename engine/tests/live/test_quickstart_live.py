"""`sage quickstart` / `sage db create` against real Postgres and Redis."""

from __future__ import annotations

import asyncio

import pytest

from sage.quickstart import ensure_database, wait_for_services
from tests.live.conftest import _admin_execute

pytestmark = pytest.mark.live


def test_services_answer_and_database_is_created_once(live_config, live_db_name):
    name = f"{live_db_name}_quickstart"
    asyncio.run(wait_for_services(live_config, wait_s=20))
    try:
        assert asyncio.run(ensure_database(live_config.database, name)) is True
        assert asyncio.run(ensure_database(live_config.database, name)) is False
    finally:
        asyncio.run(_admin_execute(live_config.database, f'DROP DATABASE IF EXISTS "{name}"'))
