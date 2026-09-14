"""A plugin that owns a table: detect, migrate, uninstall with state purge (contracts D.D, C.3)."""

from __future__ import annotations

import asyncio
import textwrap

import pytest
from sqlalchemy import inspect, select

from alembic import command
from sage.plugins.loader import discover
from sage.plugins.migrations import alembic_config, pending_heads
from sage.plugins.uninstall import uninstall_plugin
from sage.state.models import Account, Character
from sage.state.postgres import PostgresState
from sage.world.package import load_world_package

pytestmark = pytest.mark.live

CORE_HEAD = "m6n7o8p9q0r1"

MIGRATION = f'''
"""ledger entries table"""
import sqlalchemy as sa
from alembic import op

revision = "ledger000001"
down_revision = None
branch_labels = ("plg_ledger",)
depends_on = "{CORE_HEAD}"


def upgrade():
    op.create_table(
        "plg_ledger_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("note", sa.String(80)),
    )


def downgrade():
    op.drop_table("plg_ledger_entries")
'''


def _world_with_ledger(tmp_path):
    world_dir = tmp_path / "worlds" / "demo"
    (world_dir / "content").mkdir(parents=True)
    (world_dir / "world.toml").write_text(
        '[world]\nid = "demo"\nname = "Demo"\nversion = "1.0.0"\nengine = ">=0.1"\n\n'
        '[start]\nroom = "town:gate"\nrespawn = "town:gate"\n\n[plugins]\nledger = "^1"\n',
        encoding="utf-8",
    )
    (world_dir / "stats.yaml").write_text("{}\n", encoding="utf-8")
    (world_dir / "currencies.yaml").write_text("[]\n", encoding="utf-8")
    plugin = world_dir / "plugins" / "ledger"
    (plugin / "migrations" / "versions").mkdir(parents=True)
    (plugin / "sage_plugin_ledger").mkdir()
    (plugin / "sage_plugin_ledger" / "__init__.py").write_text("", encoding="utf-8")
    (plugin / "sage_plugin_ledger" / "main.py").write_text(
        "def setup(api):\n    pass\n", encoding="utf-8"
    )
    (plugin / "plugin.toml").write_text(
        textwrap.dedent(
            """
            [plugin]
            id = "ledger"
            version = "1.0.0"
            engine = ">=0.1"
            entry = "sage_plugin_ledger.main:setup"
            first_party = true

            [touches]
            tables = ["plg_ledger_entries"]
            state_blocks = ["ledger"]
            """
        ),
        encoding="utf-8",
    )
    (plugin / "migrations" / "versions" / "ledger000001_entries.py").write_text(
        MIGRATION, encoding="utf-8"
    )
    world = load_world_package(world_dir)
    records = discover(world, tmp_path / "plugins", [tmp_path / "worlds"])
    return world, records


def _tables(config) -> set[str]:
    from tests.live.test_migrations import _run_sync

    return set(_run_sync(config, lambda c: inspect(c).get_table_names()))


def test_plugin_branch_migrates_and_uninstalls(tmp_path, live_config, migrated_database):
    world, records = _world_with_ledger(tmp_path)
    db = PostgresState(live_config.database)
    cfg = alembic_config([r.path for r in records])

    assert pending_heads(cfg, db.url) == ["ledger000001"]
    command.upgrade(cfg, "heads")
    assert pending_heads(cfg, db.url) == []
    assert "plg_ledger_entries" in _tables(live_config)

    async def seed_character():
        try:
            async with db.session_factory() as session, session.begin():
                account = Account(username="ledger_owner", password_hash="x")
                session.add(account)
                await session.flush()
                session.add(
                    Character(
                        account_id=account.id,
                        name="ledger_hero",
                        room_id="town:gate",
                        stats={"hp": 9, "ledger": {"owed": 3}},
                    )
                )
        finally:
            await db.close()

    asyncio.run(seed_character())

    report = asyncio.run(uninstall_plugin(world, records, "ledger", db.url, purge_state=True))
    assert any("downgraded plg_ledger" in line for line in report), report
    assert "plg_ledger_entries" not in _tables(live_config)
    assert 'ledger = "^1"' not in (world.root / "world.toml").read_text(encoding="utf-8")

    async def read_stats():
        db2 = PostgresState(live_config.database)
        try:
            async with db2.session_factory() as session:
                row = (
                    await session.execute(select(Character).where(Character.name == "ledger_hero"))
                ).scalar_one()
                return row.stats
        finally:
            await db2.close()

    assert asyncio.run(read_stats()) == {"hp": 9}


def test_agents_branch_copies_rows_from_the_retired_engine_table(live_config, migrated_database):
    """Core head renames agent_state first; plg_agents must still find and copy the rows."""
    from sqlalchemy import text

    from tests.live.conftest import REPO_ROOT
    from tests.live.test_migrations import _run_sync

    def seed(conn):
        conn.execute(
            text(
                "INSERT INTO retired_agent_state (id, name, room_id, stats, inventory, updated_at) "
                "VALUES ('probe', 'Probe Agent', 'town:gate', '{\"hp\": 4}', '[]', now())"
            )
        )
        conn.commit()

    def copied(conn):
        return conn.execute(text("SELECT name, room_id, stats FROM plg_agents_state")).all()

    def unseed(conn):
        conn.execute(text("DELETE FROM retired_agent_state WHERE id = 'probe'"))
        conn.commit()

    cfg = alembic_config([REPO_ROOT / "plugins" / "agents"])
    _run_sync(live_config, seed)
    try:
        command.upgrade(cfg, "plg_agents@head")
        rows = _run_sync(live_config, copied)
        assert [(r.name, r.room_id, r.stats) for r in rows] == [
            ("Probe Agent", "town:gate", {"hp": 4})
        ]
    finally:
        command.downgrade(cfg, "plg_agents@base")
        _run_sync(live_config, unseed)


def test_world_plugin_branch_moves_a_legacy_column_into_its_state_block(
    live_config, migrated_database
):
    """plg_morality copies characters.reputation into stats and zeroes it; downgrade reverses."""
    from sqlalchemy import text

    from tests.live.conftest import REPO_ROOT
    from tests.live.test_migrations import _run_sync

    plugin = next((REPO_ROOT / "worlds").glob("*/plugins/morality"), None)
    if plugin is None:
        pytest.skip("no world ships the morality plugin")

    def execute(sql):
        def run(conn):
            result = conn.execute(text(sql))
            rows = result.all() if result.returns_rows else None
            conn.commit()
            return rows

        return _run_sync(live_config, run)

    execute(
        "INSERT INTO accounts (username, password_hash, is_gm, created_at) "
        "VALUES ('moral_owner', 'x', false, now())"
    )
    execute(
        "INSERT INTO characters (account_id, name, room_id, reputation, pvp_enabled, stats, "
        "inventory, created_at, updated_at) SELECT id, 'moral_hero', 'probe:start', -40, false, "
        "'{\"hp\": 3}', '[]', now(), now() FROM accounts WHERE username = 'moral_owner'"
    )
    cfg = alembic_config([plugin])
    try:
        command.upgrade(cfg, "plg_morality@head")
        [(stats, column)] = execute(
            "SELECT stats, reputation FROM characters WHERE name = 'moral_hero'"
        )
        assert stats == {"hp": 3, "morality": {"standing": -40}} and column == 0
        command.downgrade(cfg, "plg_morality@base")
        [(stats, column)] = execute(
            "SELECT stats, reputation FROM characters WHERE name = 'moral_hero'"
        )
        assert stats == {"hp": 3} and column == -40
    finally:
        command.downgrade(cfg, "plg_morality@base")
        execute("DELETE FROM characters WHERE name = 'moral_hero'")
        execute("DELETE FROM accounts WHERE username = 'moral_owner'")
