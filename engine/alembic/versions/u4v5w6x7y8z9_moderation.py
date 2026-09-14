"""moderation: sign-in history, address bans, mutes, player reports

Revision ID: u4v5w6x7y8z9
Revises: t3u4v5w6x7y8
Create Date: 2026-09-14

account_logins holds one row per sign-in; its address column is filled only while the operator
records sign-in addresses (config/moderation.toml, off by default). address_bans refuses a network
at sign-in and play. accounts gain a mute. player_reports holds the in-game report queue.
All additive, so downgrade drops them.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "u4v5w6x7y8z9"
down_revision: str | Sequence[str] | None = "t3u4v5w6x7y8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("muted_until", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("mute_reason", sa.String(length=500), nullable=True))
    op.create_table(
        "account_logins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("address", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_account_logins_account_id", "account_logins", ["account_id"])
    op.create_index("ix_account_logins_at", "account_logins", ["at"])
    op.create_index("ix_account_logins_address", "account_logins", ["address"])
    op.create_table(
        "address_bans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("network", sa.String(length=64), nullable=False, unique=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "player_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("character_name", sa.String(length=50), nullable=False),
        sa.Column("room_id", sa.String(length=255), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("staff_note", sa.String(length=2000), nullable=True),
        sa.Column("handled_by", sa.String(length=64), nullable=True),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_player_reports_created_at", "player_reports", ["created_at"])
    op.create_index("ix_player_reports_status", "player_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_player_reports_status", table_name="player_reports")
    op.drop_index("ix_player_reports_created_at", table_name="player_reports")
    op.drop_table("player_reports")
    op.drop_table("address_bans")
    op.drop_index("ix_account_logins_address", table_name="account_logins")
    op.drop_index("ix_account_logins_at", table_name="account_logins")
    op.drop_index("ix_account_logins_account_id", table_name="account_logins")
    op.drop_table("account_logins")
    op.drop_column("accounts", "mute_reason")
    op.drop_column("accounts", "muted_until")
