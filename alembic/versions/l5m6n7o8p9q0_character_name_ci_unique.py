"""characters.name unique regardless of case

Revision ID: l5m6n7o8p9q0
Revises: k4l5m6n7o8p9
Create Date: 2026-09-13

"""

from typing import Sequence, Union

from alembic import op


revision: str = "l5m6n7o8p9q0"
down_revision: Union[str, Sequence[str], None] = "k4l5m6n7o8p9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_characters_name_lower ON characters (lower(name))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_characters_name_lower")
