"""
Ensure local play accounts exist (create or reset password).

Default seeds (no arguments):
  - test / test
  - demo / demo  (generic handoff / QA login)

Custom account (e.g. after a fresh DB wiped your user):

  python engine/scripts/ensure_test_user.py Ronan your-new-password

Creates the account if missing, or resets the password if it already exists. Characters are not
created here: sign in and create one in the player UI, so the running world's start room, wallet
and character-creation plugins apply.

Run from repo root:  python engine/scripts/ensure_test_user.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Engine source on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import bcrypt
from sqlalchemy import select

from sage.core.config import load_config
from sage.state.models import Account
from sage.state.postgres import PostgresState

SEED_ACCOUNTS: tuple[tuple[str, str], ...] = (
    ("test", "test"),
    ("demo", "demo"),
)


async def ensure_account(session, username: str, password: str, starting_ai_credits: int) -> None:
    result = await session.execute(select(Account).where(Account.username == username))
    account = result.scalar_one_or_none()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    if account is None:
        session.add(
            Account(
                username=username,
                password_hash=pw_hash,
                last_login=datetime.utcnow(),
                ai_credits=int(starting_ai_credits),
            )
        )
        await session.commit()
        print(f"Created account '{username}'. Sign in to create a character.")
        return

    account.password_hash = pw_hash
    account.last_login = datetime.utcnow()
    await session.commit()
    print(f"Updated password for '{username}'.")


async def main() -> None:
    argv = sys.argv[1:]
    if len(argv) == 0:
        pairs: tuple[tuple[str, str], ...] = SEED_ACCOUNTS
    elif len(argv) == 2:
        u, p = argv[0].strip(), argv[1]
        if not u or not p:
            print("Username and password must be non-empty.", file=sys.stderr)
            sys.exit(2)
        pairs = ((u, p),)
    else:
        print(
            "Usage:\n"
            "  python engine/scripts/ensure_test_user.py\n"
            "      → create/update test+test and demo+demo\n"
            "  python engine/scripts/ensure_test_user.py <username> <password>\n"
            "      → create or reset that play account",
            file=sys.stderr,
        )
        sys.exit(2)

    config = load_config(str(_ROOT.parent / "config"))
    db = PostgresState(config.database)
    try:
        async with db.session_factory() as session:
            for username, password in pairs:
                await ensure_account(
                    session, username, password, config.comfyui.starting_ai_credits
                )
    finally:
        await db.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
