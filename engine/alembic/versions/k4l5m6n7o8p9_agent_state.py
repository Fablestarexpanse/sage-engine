"""agent_state — durable stats/inventory/room for agent NPCs

Revision ID: k4l5m6n7o8p9
Revises: j3k4l5m6n7o8
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k4l5m6n7o8p9"
down_revision: Union[str, Sequence[str], None] = "j3k4l5m6n7o8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_state",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("room_id", sa.String(length=255), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("inventory", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_state_name"), "agent_state", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_state_name"), table_name="agent_state")
    op.drop_table("agent_state")
