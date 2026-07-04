"""Dev-mode bootstrap — seed default staff and play accounts at startup.

Takes only the database and config, so server startup does not need to reach
into the admin package for account seeding (keeps server → admin coupling to
NexusApp composition only).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import bcrypt
from sqlalchemy import select

from fablestar.state.models import Account, AdminStaff

if TYPE_CHECKING:
    from fablestar.core.config import Config
    from fablestar.state.postgres import PostgresState

logger = logging.getLogger(__name__)

DEV_DEFAULT_STAFF_USERNAME = "staff"
DEV_DEFAULT_STAFF_PASSWORD = "testpass"

DEV_DEFAULT_PLAY_LOGINS: tuple[tuple[str, str, bool], ...] = (
    ("staff", "testpass", True),
    ("player", "testpass", False),
)


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def ensure_dev_default_staff(db: PostgresState, config: Config) -> None:
    """If dev_mode, ensure admin_staff staff/testpass exists (head_admin). Create-only."""
    if not getattr(config.server, "dev_mode", False):
        return
    async with db.session_factory() as session:
        r = await session.execute(
            select(AdminStaff).where(AdminStaff.username == DEV_DEFAULT_STAFF_USERNAME)
        )
        if r.scalar_one_or_none() is not None:
            return
        session.add(
            AdminStaff(
                username=DEV_DEFAULT_STAFF_USERNAME,
                password_hash=_hash_password(DEV_DEFAULT_STAFF_PASSWORD),
                display_name="Dev staff",
                role="head_admin",
                is_active=True,
                permissions={},
            )
        )
        await session.commit()
    logger.warning(
        "dev_mode: created default Nexus login %r / %r (head_admin)",
        DEV_DEFAULT_STAFF_USERNAME,
        DEV_DEFAULT_STAFF_PASSWORD,
    )


async def ensure_dev_default_play_accounts(db: PostgresState, config: Config) -> None:
    """If dev_mode, ensure the default play logins exist. Create-only."""
    if not getattr(config.server, "dev_mode", False):
        return
    start_credits = int(config.comfyui.starting_echo_credits)
    for username, password, is_gm in DEV_DEFAULT_PLAY_LOGINS:
        async with db.session_factory() as session:
            r = await session.execute(select(Account).where(Account.username == username))
            if r.scalar_one_or_none() is not None:
                continue
            session.add(
                Account(
                    username=username,
                    password_hash=_hash_password(password),
                    echo_credits=start_credits,
                    is_gm=is_gm,
                )
            )
            await session.commit()
            logger.warning(
                "dev_mode: created play login %r / %r (is_gm=%s)",
                username,
                password,
                is_gm,
            )


async def ensure_dev_defaults(db: PostgresState, config: Config) -> None:
    """Best-effort dev-mode seeding; failures are logged, never fatal."""
    try:
        await ensure_dev_default_staff(db, config)
    except Exception as e:
        logger.warning("Default dev staff account not ensured: %s", e)
    try:
        await ensure_dev_default_play_accounts(db, config)
    except Exception as e:
        logger.warning("Default dev play accounts not ensured: %s", e)
