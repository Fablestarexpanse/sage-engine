"""
Create the first head admin account (run once after migrations).

Usage:
  python scripts/bootstrap_admin.py --username admin --password secret

Requires PostgreSQL and admin_staff table (alembic upgrade head).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Repo root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sage.core.config import load_config
from sage.state.postgres import PostgresState
from sage.admin import staff_service


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--display-name", default="", help="Defaults to username")
    args = p.parse_args()

    config = load_config()
    db = PostgresState(config.database)
    server = type("S", (), {"db": db, "config": config})()

    rows = await staff_service.list_staff(server)
    if any(r.role == "head_admin" and r.is_active for r in rows):
        print("A head_admin already exists. Use the admin UI (Team) or patch via DB.")
        await db.close()
        raise SystemExit(1)

    dn = (args.display_name or args.username).strip()
    await staff_service.create_staff(
        server,
        username=args.username,
        password=args.password,
        display_name=dn,
        role="head_admin",
        permissions={},
    )
    print(f"Created head_admin '{args.username}'. Enable admin_auth_required in config/server.toml when ready.")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
