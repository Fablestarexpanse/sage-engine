"""character snapshots

Revision ID: t3u4v5w6x7y8
Revises: s2t3u4v5w6x7
Create Date: 2026-09-14

Before a staff member changes a character (move, money, items, vitals, the account editor), the
character's room, stats and inventory are saved, so the change can be undone from the console.
Additive, so downgrade drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "t3u4v5w6x7y8"
down_revision: str | Sequence[str] | None = "s2t3u4v5w6x7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "character_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("staff_username", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.String(length=255), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inventory", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_character_snapshots_character_id", "character_snapshots", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_character_snapshots_character_id", table_name="character_snapshots")
    op.drop_table("character_snapshots")
