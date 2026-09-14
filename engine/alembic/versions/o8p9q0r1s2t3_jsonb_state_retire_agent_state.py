"""characters.stats/inventory become JSONB; agent_state is renamed retired_agent_state

Revision ID: o8p9q0r1s2t3
Revises: n7o8p9q0r1s2
Create Date: 2026-09-14

Contracts D.D (locked decision 5): character state is JSONB so plugin blocks can be queried and
indexed. Reversible: downgrade casts back to JSON.

agent_state moved to the agents plugin (plg_agents_state, branch plg_agents). A core revision may
run before the plugin branch in one `upgrade heads`, so this step only renames the table; the
plugin copies from either name, and a later core revision drops retired_agent_state.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "o8p9q0r1s2t3"
down_revision: str | Sequence[str] | None = "n7o8p9q0r1s2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("stats", "inventory"):
        op.alter_column(
            "characters",
            column,
            type_=postgresql.JSONB(),
            existing_type=sa.JSON(),
            postgresql_using=f"{column}::jsonb",
        )
    op.rename_table("agent_state", "retired_agent_state")
    op.execute("ALTER INDEX ix_agent_state_name RENAME TO ix_retired_agent_state_name")


def downgrade() -> None:
    op.execute("ALTER INDEX ix_retired_agent_state_name RENAME TO ix_agent_state_name")
    op.rename_table("retired_agent_state", "agent_state")
    for column in ("stats", "inventory"):
        op.alter_column(
            "characters",
            column,
            type_=sa.JSON(),
            existing_type=postgresql.JSONB(),
            postgresql_using=f"{column}::json",
        )
