"""label the core migration chain sage_core

Plugins ship their own alembic branches (label ``plg_<plugin id>``) that depend on a core
revision; this empty revision gives the core chain the ``sage_core`` label so both can be
addressed by name (docs/sage/PHASE1_CONTRACTS.md D.D).

Revision ID: m6n7o8p9q0r1
Revises: l5m6n7o8p9q0
Create Date: 2026-09-13

"""

from collections.abc import Sequence

revision: str = "m6n7o8p9q0r1"
down_revision: str | Sequence[str] | None = "l5m6n7o8p9q0"
branch_labels: str | Sequence[str] | None = ("sage_core",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
