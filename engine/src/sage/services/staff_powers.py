"""Who has staff power in the game, and what they may do.

A player has staff power when their account wears the GM crown (``accounts.is_gm``) and an active
Nexus staff account uses the same name (the account editor's "Nexus console access"). That staff
account's role, tools and zones decide what the in-game staff commands allow, exactly as in the
console, and every use is written to the same audit log. The crown alone grants nothing, so a
head admin always controls what a GM can do.
"""

from __future__ import annotations

from typing import Any

# What each in-game staff command needs (any one of the tools).
COMMAND_TOOLS: dict[str, tuple[str, ...]] = {
    "goto": ("players", "world"),
    "at": ("players", "world"),
    "where": ("players", "world"),
    "stat": ("players", "world"),
    "transfer": ("players",),
    "restore": ("players",),
    "mute": ("players",),
    "unmute": ("players",),
    "staff": ("players", "world"),
}


async def staff_context(server: Any, session: Any) -> Any | None:
    """The staff context behind a playing session, or None when it has no staff power."""
    from sqlalchemy import select

    from sage.admin.admin_security import AdminContext
    from sage.state.models import Account, AdminStaff

    account_id = getattr(session, "account_id", None)
    if account_id is None or getattr(session, "virtual", False):
        return None
    async with server.db.session_factory() as db:
        account = await db.get(Account, account_id)
        if account is None or not account.is_gm:
            return None
        row = (
            await db.execute(
                select(AdminStaff).where(AdminStaff.username == account.username.strip().lower())
            )
        ).scalar_one_or_none()
    if row is None or not row.is_active:
        return None
    return AdminContext.from_staff(row)


def may_use(ctx: Any, verb: str) -> bool:
    return any(ctx.may_use_tool(tool) for tool in COMMAND_TOOLS.get(verb, ()))
