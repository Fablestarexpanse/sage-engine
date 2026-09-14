"""admin audit log and account suspension

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-09-14

Staff actions in the admin console are recorded (who, what, which target, details) so a change to
an account, character, lexicon line, template or staff member can be traced. Accounts gain a
suspension timestamp and reason; a suspended account cannot sign in or use a play token.
Both are additive, so downgrade drops them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "s2t3u4v5w6x7"
down_revision: str | Sequence[str] | None = "r1s2t3u4v5w6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("staff_username", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"])
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.add_column("accounts", sa.Column("suspended_at", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("suspended_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "suspended_reason")
    op.drop_column("accounts", "suspended_at")
    op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
