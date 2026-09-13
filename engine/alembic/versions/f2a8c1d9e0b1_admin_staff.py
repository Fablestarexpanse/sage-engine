"""admin_staff

Revision ID: f2a8c1d9e0b1
Revises: ec5a13557ef4
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a8c1d9e0b1"
down_revision: Union[str, Sequence[str], None] = "ec5a13557ef4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_staff",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_staff_username"), "admin_staff", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_staff_username"), table_name="admin_staff")
    op.drop_table("admin_staff")
