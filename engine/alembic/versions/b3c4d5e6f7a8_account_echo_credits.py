"""account echo_credits for ComfyUI economy

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("echo_credits", sa.Integer(), nullable=False, server_default="0"),
    )
    # One-time grant for existing accounts (matches default starting_echo_credits in config).
    op.execute(sa.text("UPDATE accounts SET echo_credits = 50"))


def downgrade() -> None:
    op.drop_column("accounts", "echo_credits")
