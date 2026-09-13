"""character portrait fields

Revision ID: a1b2c3d4e5f6
Revises: f2a8c1d9e0b1
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f2a8c1d9e0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("portrait_url", sa.String(length=2048), nullable=True))
    op.add_column("characters", sa.Column("portrait_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("characters", "portrait_prompt")
    op.drop_column("characters", "portrait_url")
