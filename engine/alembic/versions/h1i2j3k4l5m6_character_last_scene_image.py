"""character last_scene_image_url for persisted player scene art

Revision ID: h1i2j3k4l5m6
Revises: g7h8i9j0k1l2
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("last_scene_image_url", sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "last_scene_image_url")
