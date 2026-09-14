"""plg_agents_state: durable agent state, copied from the engine's former agent_state table.

Revision ID: agents0001
Branch: plg_agents
Create Date: 2026-09-13

One-way door (owner ruling 2026-09-13): existing rows are copied from the engine's old table,
under whichever name it has when this runs (agent_state, or retired_agent_state after core
o8p9q0r1s2t3); a later core migration drops it. Downgrading this branch
(plugin uninstall) drops plg_agents_state and its data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agents0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("plg_agents",)
depends_on: str | Sequence[str] | None = "n7o8p9q0r1s2"


def upgrade() -> None:
    op.create_table(
        "plg_agents_state",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("room_id", sa.String(length=255), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("inventory", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plg_agents_state_name", "plg_agents_state", ["name"], unique=False)
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    source = next((t for t in ("retired_agent_state", "agent_state") if t in tables), None)
    if source is not None:
        op.execute(
            "INSERT INTO plg_agents_state (id, name, room_id, stats, inventory, updated_at) "
            f"SELECT id, name, room_id, stats, inventory, updated_at FROM {source}"
        )


def downgrade() -> None:
    op.drop_index("ix_plg_agents_state_name", table_name="plg_agents_state")
    op.drop_table("plg_agents_state")
