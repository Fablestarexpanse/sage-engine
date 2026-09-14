"""wallet balances move from the legacy characters wallet column into the stats blob

Revision ID: p9q0r1s2t3u4
Revises: o8p9q0r1s2t3
Create Date: 2026-09-14

Until now the column was the durable copy of the primary balance: login copied it into stats and
every flush mirrored stats back. From this revision the stats blob, under the running world's
primary currency key (currencies.yaml), is the only copy. Backfill, not drop: the column stays
until a later revision, so downgrade copies the stats balance back and the old code keeps working.

One database per world (contracts B.8), so the configured world's primary currency is the right
key for every row. A world without currencies has nothing to move.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p9q0r1s2t3u4"
down_revision: str | Sequence[str] | None = "o8p9q0r1s2t3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The pre-SAGE column (migration d5e6f7a8b9c0); named once here, dropped in a later revision.
LEGACY_COLUMN = "digi_balance"


def _primary_currency_key() -> str | None:
    from sage.core.config import load_config, resolve_project_root
    from sage.world.package import select_world

    config = load_config()
    world = select_world(resolve_project_root() / config.server.worlds_dir, config.server.world)
    return world.currencies[0].key if world.currencies else None


def upgrade() -> None:
    key = _primary_currency_key()
    if key is None:
        return
    op.get_bind().execute(
        sa.text(
            "UPDATE characters SET stats = jsonb_set("
            f"coalesce(stats, '{{}}'::jsonb), ARRAY[:key], to_jsonb(coalesce({LEGACY_COLUMN}, 0)), true)"
        ),
        {"key": key},
    )


def downgrade() -> None:
    key = _primary_currency_key()
    if key is None:
        return
    op.get_bind().execute(
        sa.text(
            f"UPDATE characters SET {LEGACY_COLUMN} = "
            f"coalesce((stats ->> :key)::integer, {LEGACY_COLUMN})"
        ),
        {"key": key},
    )
