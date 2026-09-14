"""world_overrides persistence for live lexicon edits (decision 7, contracts B.7)."""

from __future__ import annotations

import asyncio

import pytest

from sage.lexicon.overrides import LexiconOverrides, OverrideError
from sage.state.postgres import PostgresState

pytestmark = pytest.mark.live


def test_versions_rollback_and_clear_against_postgres(live_config, migrated_database):
    async def run():
        db = PostgresState(live_config.database)
        try:
            store = LexiconOverrides(db.session_factory)
            assert await store.save("login.motd", "First", author_staff_id=None, note="v1") == 1
            assert await store.save("login.motd", "Second", author_staff_id=None) == 2
            assert await store.active() == {"login.motd": "Second"}

            await store.rollback("login.motd", 1)
            assert await store.active() == {"login.motd": "First"}
            history = await store.history("login.motd")
            assert [(h["version"], h["active"], h["note"]) for h in history] == [
                (2, False, None),
                (1, True, "v1"),
            ]
            with pytest.raises(OverrideError):
                await store.rollback("login.motd", 7)

            await store.clear("login.motd")
            assert await store.active() == {}
            assert len(await store.history("login.motd")) == 2  # history is kept
        finally:
            await db.close()

    asyncio.run(run())
