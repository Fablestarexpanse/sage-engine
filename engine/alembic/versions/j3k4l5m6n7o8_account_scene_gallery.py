"""account_scene_images gallery for player scene art history

Revision ID: j3k4l5m6n7o8
Revises: h1i2j3k4l5m6
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j3k4l5m6n7o8"
down_revision: Union[str, Sequence[str], None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_scene_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=2048), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=True),
        sa.Column("prompt_preview", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_scene_images_account_id"),
        "account_scene_images",
        ["account_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_account_scene_images_account_id"), table_name="account_scene_images")
    op.drop_table("account_scene_images")
