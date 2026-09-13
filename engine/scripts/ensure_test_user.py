"""
Ensure local play accounts exist (create or reset password).

Default seeds (no arguments):
  - test / test
  - demo / demo  (generic handoff / QA login)

Custom account (e.g. after a fresh DB wiped your user):

  python engine/scripts/ensure_test_user.py Ronan your-new-password

Creates the account if missing, or resets the password if it already exists.

Run from repo root:  python engine/scripts/ensure_test_user.py
Requires PYTHONPATH=src (or pip install -e .).
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Repo root on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import bcrypt
from sqlalchemy import select

from sage.core.config import load_config
from sage.state.models import Account, Character
from sage.state.postgres import PostgresState

# (username, password) — character name matches username for a default spawn.
SEED_ACCOUNTS: tuple[tuple[str, str], ...] = (
    ("test", "test"),
    ("demo", "demo"),
)


async def ensure_account(session, username: str, password: str, starting_echo: int, starting_digi: int) -> None:
    result = await session.execute(select(Account).where(Account.username == username))
    account = result.scalar_one_or_none()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    if account is None:
        account = Account(
            username=username,
            password_hash=pw_hash,
            last_login=datetime.utcnow(),
            echo_credits=int(starting_echo),
        )
        session.add(account)
        await session.flush()
        session.add(
            Character(
                account_id=account.id,
                name=username,
                room_id="test_zone:entrance",
                digi_balance=int(starting_digi),
            )
        )
        await session.commit()
        print(f"Created account '{username}' with default character.")
        return

    account.password_hash = pw_hash
    account.last_login = datetime.utcnow()
    result = await session.execute(select(Character).where(Character.account_id == account.id))
    chars = list(result.scalars().all())
    if not chars:
        session.add(
            Character(
                account_id=account.id,
                name=username,
                room_id="test_zone:entrance",
                digi_balance=int(starting_digi),
            )
        )
    await session.commit()
    print(f"Updated password for '{username}' (and added character if missing).")


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
    starting_echo = int(config.comfyui.starting_echo_credits)
    starting_digi = int(config.server.starting_digi_balance)
    try:
        async with db.session_factory() as session:
            for username, password in pairs:
                await ensure_account(session, username, password, starting_echo, starting_digi)
    finally:
        await db.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
