"""Brief invariant 5: every reference world boots on the same engine and can be played.

For each world package, start a real ``python -m sage`` process against the live tier's
throwaway database and Redis db 15, dev-login a character, and play a short script over the
WebSocket: arrive in the world's start room, say something, walk an exit and back, quit.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
import websockets

from sage.world.package import available_worlds, load_world_package
from tests.live.conftest import REPO_ROOT, _admin_execute, open_redis

pytestmark = pytest.mark.live

WORLDS = available_worlds(REPO_ROOT / "worlds")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.load(response)


def _post(url: str, body: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


async def _play(port: int, lines: list[str]) -> list[str]:
    login = _post(f"http://127.0.0.1:{port}/play/dev/login", {"character": "Smoke Tester"})
    text: list[str] = []
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws/play") as ws:
        await ws.send(
            json.dumps({"token": login["play_token"], "character_id": login["character_id"]})
        )

        async def until_prompt(wait_s: float = 30.0) -> None:
            """Read frames until the command prompt comes back (or the server closes)."""
            deadline = asyncio.get_running_loop().time() + wait_s
            try:
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    frame = await asyncio.wait_for(ws.recv(), max(remaining, 0.01))
                    if frame.lstrip().startswith("{"):
                        continue
                    text.append(frame)
                    if frame.rstrip(" ").endswith(">"):
                        return
            except (TimeoutError, websockets.ConnectionClosed):
                return

        await until_prompt(wait_s=60.0)
        for line in lines:
            await ws.send(line)
            await until_prompt()
    return text


def _first_exit(world) -> tuple[str, str]:
    import yaml

    zone, slug = world.start_room.split(":")
    room = yaml.safe_load((world.zones_dir / zone / "rooms" / f"{slug}.yaml").read_text("utf-8"))
    direction, exit_meta = next(iter(room["exits"].items()))
    return direction, exit_meta["destination"]


OPPOSITE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "down",
    "down": "up",
}


@pytest.fixture
def world_database(live_config, live_database, world_id):
    """One database per world (owner ruling): each world's plugin branches stay separate."""
    db = live_config.database
    name = f"{live_database}_{world_id}"
    asyncio.run(_admin_execute(db, f'CREATE DATABASE "{name}"'))
    try:
        yield name
    finally:
        asyncio.run(
            _admin_execute(
                db,
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
                f'DROP DATABASE IF EXISTS "{name}"',
            )
        )


@pytest.mark.parametrize("world_id", WORLDS)
def test_world_boots_and_plays(world_id, live_config, world_database, tmp_path):
    world = load_world_package(REPO_ROOT / "worlds" / world_id)
    direction, destination = _first_exit(world)
    port = _free_port()

    async def flush():
        async with open_redis(live_config):
            pass

    asyncio.run(flush())
    env = {
        **os.environ,
        "SAGE_SERVER__WORLD": world_id,
        "SAGE_DATABASE__DATABASE": world_database,
        "SAGE_SERVER__WEBSOCKET_PORT": str(port),
        "SAGE_SERVER__DEV_MODE": "true",
        "SAGE_SERVER__DEV_LOGIN": "true",
        "SAGE_ADMIN_JWT_SECRET": secrets.token_hex(32),
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    # Deploy the way an operator does: apply the world's plugin migrations, then boot.
    upgrade = subprocess.run(
        [sys.executable, "-m", "sage", "db", "upgrade"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    log_path = tmp_path / f"{world_id}.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "sage"],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 90
            while True:
                if proc.poll() is not None:
                    pytest.fail(
                        f"{world_id} server exited early:\n{log_path.read_text('utf-8', errors='replace')[-4000:]}"
                    )
                try:
                    if _get(f"http://127.0.0.1:{port}/play/health").get("ok"):
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    pytest.fail(
                        f"{world_id} server never became healthy:\n{log_path.read_text('utf-8', errors='replace')[-4000:]}"
                    )
                time.sleep(0.5)

            # Clients title themselves from this; it must be the package's name, not a default.
            assert _get(f"http://127.0.0.1:{port}/play/world") == {
                "id": world_id,
                "name": world.manifest.world.name,
            }
            back = OPPOSITE.get(direction, direction)
            text = "\n".join(
                asyncio.run(_play(port, ["say smoke test", direction, back, "who", "quit"]))
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()

    server_log = log_path.read_text("utf-8", errors="replace")
    print(f"--- {world_id} transcript ---\n{text}")  # shown with -s or on failure
    assert f"World: {world_id}" in server_log
    assert f"[ {world.start_room} ]" in text, text
    assert f"[ {destination} ]" in text, text
    assert 'You say: "smoke test"' in text, text
    assert "Goodbye" in text, text
    assert "[" + "missing" not in text
    unresolved = [
        line
        for line in text.splitlines()
        if line.strip().startswith("[") and line.strip().endswith("]") and " " not in line.strip()
    ]
    assert unresolved == [], f"unresolved lexicon keys: {unresolved}"
    assert "Traceback" not in server_log, server_log[-4000:]
