"""morality: characters' moral standing moves from the engine column into the plugin's state block

Revision ID: morality0001
Branch: plg_morality
Create Date: 2026-09-14

Copies characters.reputation into stats.morality.standing (when that column still exists) and
zeroes the column, so the core revision that drops it can tell nothing is left behind. Downgrade
copies the standing back and removes the block. Adds no tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "morality0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("plg_morality",)
depends_on: str | Sequence[str] | None = "q0r1s2t3u4v5"


def _has_column() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns("characters")
    return any(c["name"] == "reputation" for c in columns)


def upgrade() -> None:
    if not _has_column():
        return
    op.execute(
        "UPDATE characters SET stats = jsonb_set(coalesce(stats, '{}'::jsonb), '{morality}', "
        "coalesce(stats -> 'morality', '{}'::jsonb) || jsonb_build_object('standing', reputation)), "
        "reputation = 0 WHERE reputation <> 0 OR NOT (coalesce(stats, '{}'::jsonb) ? 'morality')"
    )


def downgrade() -> None:
    if not _has_column():
        return
    op.execute(
        "UPDATE characters SET reputation = coalesce((stats -> 'morality' ->> 'standing')::integer, 0), "
        "stats = stats - 'morality'"
    )
