"""drop the legacy wallet and standing columns and the retired agent table

Revision ID: r1s2t3u4v5w6
Revises: q0r1s2t3u4v5
Create Date: 2026-09-14

Phase 3.14d (contracts D.D one-way doors). Every value already lives elsewhere:
- wallet balances in characters.stats under the world's primary currency (p9q0r1s2t3u4);
- moral standing in a world plugin's state block (for example plg_morality, which copies and zeroes it);
- agent rows in plg_agents_state (agents0001).

The upgrade refuses while any character still has a non-zero standing column, because that
means the world plugin that owns the value has not migrated yet. Downgrade re-creates the
columns (zero) and an empty table; running the earlier downgrades after it (p9q0r1s2t3u4,
plg_morality) copies the values back from stats.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r1s2t3u4v5w6"
down_revision: str | Sequence[str] | None = "q0r1s2t3u4v5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Pre-SAGE column names (migrations d5e6f7a8b9c0, f6e7d8c9b0a1), named once.
LEGACY_WALLET = "digi_balance"
LEGACY_STANDING = "reputation"


def upgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(
        sa.text(f"SELECT count(*) FROM characters WHERE {LEGACY_STANDING} <> 0")
    ).scalar_one()
    if held:
        raise RuntimeError(
            f"{held} character(s) still hold a {LEGACY_STANDING} value: run the world plugin "
            f"migration that owns it first (for example `alembic upgrade plg_morality@head`, "
            f"then `sage db upgrade`), or set the column to 0 if the world does not use it"
        )
    op.drop_column("characters", LEGACY_WALLET)
    op.drop_column("characters", LEGACY_STANDING)
    if "retired_agent_state" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_retired_agent_state_name", table_name="retired_agent_state")
        op.drop_table("retired_agent_state")


def downgrade() -> None:
    op.create_table(
        "retired_agent_state",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("room_id", sa.String(length=255), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("inventory", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retired_agent_state_name", "retired_agent_state", ["name"], unique=False)
    op.add_column(
        "characters",
        sa.Column(LEGACY_STANDING, sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "characters",
        sa.Column(LEGACY_WALLET, sa.Integer(), nullable=False, server_default="0"),
    )
