"""world_overrides: versioned live edits to world lexicon (and later prompts/style)

Revision ID: n7o8p9q0r1s2
Revises: m6n7o8p9q0r1
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n7o8p9q0r1s2"
down_revision: str | Sequence[str] | None = "m6n7o8p9q0r1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "world_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("author_staff_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_world_overrides_kind_key", "world_overrides", ["kind", "key"])


def downgrade() -> None:
    op.drop_index("ix_world_overrides_kind_key", table_name="world_overrides")
    op.drop_table("world_overrides")
