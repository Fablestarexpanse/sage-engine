"""`sage quickstart`: from a fresh checkout to a running server in one command.

Steps, each skipped when already done:

1. Config: write `.env`, `config/server.toml` and `config/database.toml` when they are missing,
   from the `*.example.toml` files, with a generated database password and JWT secret. Existing
   files are never changed. Generated secrets are never printed.
2. Services: `docker compose up -d redis postgres`, then wait until both accept connections.
3. Database: create the world's database if it does not exist (one database per world).
4. Migrations: apply core and plugin migrations (`sage db upgrade`).
5. Server: run it (unless `--no-server`).

The world is `--world`, else the configured world, else `demo`. A world other than the configured
one uses the database `sage_<world>`, so switching worlds never mixes their data.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_WORLD = "demo"
WORLD_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class QuickstartError(Exception):
    """A step cannot continue; the message says how to fix it."""


@dataclass
class ConfigResult:
    written: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _set_toml_line(text: str, key: str, value: str) -> str:
    """Replace `key = ...` (or a commented `# key = ...`) with `key = value`; append if absent."""
    line = re.compile(rf"^#?\s*{re.escape(key)}\s*=.*$", re.M)
    if line.search(text):
        return line.sub(lambda _m: f"{key} = {value}", text, count=1)
    return text.rstrip("\n") + f"\n{key} = {value}\n"


def _toml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def ensure_config(root: Path, world: str) -> ConfigResult:
    """Write missing `.env`, `config/server.toml` and `config/database.toml`; keep existing ones."""
    result = ConfigResult()
    env_path = root / ".env"
    server_path = root / "config" / "server.toml"
    database_path = root / "config" / "database.toml"

    env = _read_env(env_path)
    existing_db_password = None
    if database_path.is_file():
        import tomllib

        existing_db_password = tomllib.loads(database_path.read_text(encoding="utf-8")).get(
            "password"
        )
    password = env.get("POSTGRES_PASSWORD") or existing_db_password or secrets.token_urlsafe(24)

    if "POSTGRES_PASSWORD" not in env:
        prefix = (
            env_path.read_text(encoding="utf-8").rstrip("\n") + "\n" if env_path.is_file() else ""
        )
        env_path.write_text(
            prefix
            + "# Written by `sage quickstart`: the database password docker compose gives Postgres.\n"
            + f"POSTGRES_PASSWORD={password}\n",
            encoding="utf-8",
        )
        result.written.append(".env")
    else:
        result.kept.append(".env")

    if not server_path.is_file():
        text = (root / "config" / "server.example.toml").read_text(encoding="utf-8")
        text = _set_toml_line(text, "world", _toml_str(world))
        text = _set_toml_line(text, "dev_mode", "true")
        # DEV-AUTH:BEGIN — quickstart turns on passwordless loopback logins; stripped for release.
        text = _set_toml_line(text, "dev_login", "true")
        # DEV-AUTH:END
        text = _set_toml_line(text, "admin_jwt_secret", _toml_str(secrets.token_hex(32)))
        header = "# Written by `sage quickstart` for local development. Edit freely; quickstart never overwrites it.\n"
        server_path.write_text(header + text, encoding="utf-8")
        result.written.append("config/server.toml")
    else:
        result.kept.append("config/server.toml")

    if not database_path.is_file():
        text = (root / "config" / "database.example.toml").read_text(encoding="utf-8")
        text = _set_toml_line(text, "password", _toml_str(password))
        text = _set_toml_line(text, "database", _toml_str(f"sage_{world}"))
        if env.get("POSTGRES_USER"):
            text = _set_toml_line(text, "user", _toml_str(env["POSTGRES_USER"]))
        database_path.write_text(text, encoding="utf-8")
        result.written.append("config/database.toml")
    else:
        result.kept.append("config/database.toml")
    return result


def database_for(world: str, configured_world: str | None, configured_database: str) -> str:
    """The configured database for the configured world; `sage_<world>` for any other world."""
    return configured_database if world == configured_world else f"sage_{world}"


def docker_up(root: Path) -> None:
    if shutil.which("docker") is None:
        raise QuickstartError(
            "Docker is not installed or not on PATH. Install Docker Desktop (or Docker Engine), "
            "start it, and run `sage quickstart` again. Already running Postgres and Redis "
            "yourself? Use `sage quickstart --no-docker`."
        )
    proc = subprocess.run(
        ["docker", "compose", "up", "-d", "redis", "postgres"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        hint = ""
        joined = " ".join(detail).lower()
        if "port is already allocated" in joined or "address already in use" in joined:
            hint = (
                " Another program holds port 5432 or 6379: stop it, or run Postgres and Redis "
                "yourself and use `sage quickstart --no-docker`."
            )
        elif "cannot connect" in joined or "daemon" in joined:
            hint = " Is Docker running? Start Docker Desktop and try again."
        last = detail[-1] if detail else "no output"
        raise QuickstartError(f"`docker compose up` failed: {last}.{hint}")


async def wait_for_services(config, wait_s: float = 90.0) -> None:
    import asyncpg
    import redis.asyncio as aioredis

    db = config.database
    deadline = time.monotonic() + wait_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(
                host=db.host,
                port=db.port,
                user=db.user,
                password=db.password,
                database="postgres",
                timeout=3,
            )
            await conn.close()
            client = aioredis.Redis(
                host=config.redis.host,
                port=config.redis.port,
                password=config.redis.password,
                socket_connect_timeout=3,
            )
            try:
                await client.ping()
            finally:
                await client.aclose()
            return
        except Exception as exc:
            last_error = exc
            if isinstance(exc, asyncpg.InvalidPasswordError):
                break
            await asyncio.sleep(1)
    if isinstance(last_error, asyncpg.InvalidPasswordError):
        raise QuickstartError(
            f"Postgres rejected user {db.user!r}: config/database.toml and .env disagree, or the "
            "Postgres data volume was created with a different password or user. Make them match "
            "(POSTGRES_PASSWORD / POSTGRES_USER in .env, password / user in config/database.toml)."
        )
    raise QuickstartError(
        f"Postgres ({db.host}:{db.port}) or Redis ({config.redis.host}:{config.redis.port}) did not "
        f"accept connections within {wait_s:.0f}s: {last_error}"
    )


async def ensure_database(db, name: str) -> bool:
    """Create database `name` if it is missing. True when it was created."""
    import asyncpg

    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise QuickstartError(f"database name {name!r} must be letters, digits and underscores")
    conn = await asyncpg.connect(
        host=db.host, port=db.port, user=db.user, password=db.password, database="postgres"
    )
    try:
        if await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            return False
        await conn.execute(f'CREATE DATABASE "{name}"')
        return True
    finally:
        await conn.close()


def run(
    world: str | None = None,
    *,
    docker: bool = True,
    server: bool = True,
    root: Path | None = None,
    say=print,
) -> int:
    from sage.core.config import load_config, resolve_project_root

    root = root or resolve_project_root()
    if world is not None and not WORLD_ID.fullmatch(world):
        raise QuickstartError(f"world id {world!r}: use lowercase letters, digits and underscores")

    configured = None
    if (root / "config" / "server.toml").is_file():
        configured = load_config(str(root / "config")).server.world
    world = world or configured or DEFAULT_WORLD
    if not (root / "worlds" / world / "world.toml").is_file():
        raise QuickstartError(f"no world package at worlds/{world}/ (world.toml not found)")

    say(f"[1/5] config for world {world!r}")
    result = ensure_config(root, world)
    for name in result.written:
        say(f"      wrote {name}")
    for name in result.kept:
        say(f"      kept  {name} (already there)")

    config = load_config(str(root / "config"))
    database = database_for(world, config.server.world, config.database.database)
    os.environ["SAGE_SERVER__WORLD"] = world
    os.environ["SAGE_DATABASE__DATABASE"] = database
    config = load_config(str(root / "config"))

    if docker:
        say("[2/5] starting Postgres and Redis (docker compose)")
        docker_up(root)
    else:
        say("[2/5] using Postgres and Redis already running (--no-docker)")
    asyncio.run(wait_for_services(config))

    created = asyncio.run(ensure_database(config.database, database))
    say(f"[3/5] database {database!r} " + ("created" if created else "already exists"))

    say("[4/5] applying migrations")
    # A separate process, as an operator would run it: Alembic configures logging for its own run,
    # and in this process that would double every server log line afterwards.
    upgrade = subprocess.run([sys.executable, "-m", "sage", "db", "upgrade"], cwd=root)
    if upgrade.returncode != 0:
        raise QuickstartError("`sage db upgrade` failed; its output is above.")

    if not server:
        say("[5/5] skipped (--no-server). Start it with: python -m sage")
        return 0
    port = config.server.websocket_port
    say(f"[5/5] starting the server for {world!r} on port {port} (Ctrl+C stops it)")
    say(
        "      player client: cd engine/clients/player-ui && npm install && "
        f"VITE_NEXUS_PORT={port} npm run dev   ->  http://localhost:5173"
    )
    from sage.server import run_server

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass
    return 0
