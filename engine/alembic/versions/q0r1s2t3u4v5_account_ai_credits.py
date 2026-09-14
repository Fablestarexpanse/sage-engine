"""accounts: the AI art balance column becomes ai_credits

Revision ID: q0r1s2t3u4v5
Revises: p9q0r1s2t3u4
Create Date: 2026-09-14

Out-of-world credit for AI portraits and scene art is an engine ledger (contracts D.D); its column
carried a world-specific name. A rename, so downgrade restores the old name with the data intact.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "q0r1s2t3u4v5"
down_revision: str | Sequence[str] | None = "p9q0r1s2t3u4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The pre-SAGE column name (migration b3c4d5e6f7a8), named once.
LEGACY_COLUMN = "echo_credits"


def upgrade() -> None:
    op.alter_column("accounts", LEGACY_COLUMN, new_column_name="ai_credits")


def downgrade() -> None:
    op.alter_column("accounts", "ai_credits", new_column_name=LEGACY_COLUMN)
