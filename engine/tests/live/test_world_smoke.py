"""Brief invariant 5: every reference world boots on the same engine and can be played.

For each world package, start a real ``python -m sage`` process against the live tier's
throwaway database and Redis db 15, register an account and create a character, and play a short script over the
WebSocket: arrive in the world's start room, say something, walk an exit and back, quit.
The second reference world also plays its loop: shop in silver, gear up, fight, level, eat, rest.
"""

from __future__ import annotations

import asyncio
import contextlib
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


def _new_character(port: int, name: str) -> tuple[str, int]:
    """Register an account and create a character the way the player client does."""
    base = f"http://127.0.0.1:{port}"
    account = _post(
        f"{base}/play/auth/register",
        {"username": f"smoke-{secrets.token_hex(4)}", "password": secrets.token_urlsafe(16)},
    )
    assert account.get("ok"), account
    token = account["play_token"]
    created = _post(f"{base}/play/characters/create", {"token": token, "name": name})
    assert created.get("ok"), created
    return token, created["character"]["id"]


async def _play(port: int, lines: list[str]) -> list[str]:
    token, character_id = _new_character(port, "Smoke Tester")
    text: list[str] = []
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws/play") as ws:
        await ws.send(json.dumps({"token": token, "character_id": character_id}))

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
            if line.startswith("#wait "):  # let the world tick (spawns, effects)
                await asyncio.sleep(float(line.split()[1]))
                continue
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


@contextlib.contextmanager
def _running_world(world_id: str, live_config, database: str, tmp_path):
    """Migrate the world's database, boot a server for it, yield (port, log path), stop it."""
    port = _free_port()

    async def flush():
        async with open_redis(live_config):
            pass

    asyncio.run(flush())
    env = {
        **os.environ,
        "SAGE_SERVER__WORLD": world_id,
        "SAGE_DATABASE__DATABASE": database,
        "SAGE_SERVER__WEBSOCKET_PORT": str(port),
        # Character creation would otherwise ask a developer's local ComfyUI for a portrait.
        "SAGE_COMFYUI__ENABLED": "false",
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
            yield port, log_path
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()


def _unresolved_keys(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip().startswith("[") and line.strip().endswith("]") and " " not in line.strip()
    ]


@pytest.mark.parametrize("world_id", WORLDS)
def test_world_boots_and_plays(world_id, live_config, world_database, tmp_path):
    world = load_world_package(REPO_ROOT / "worlds" / world_id)
    direction, destination = _first_exit(world)
    with _running_world(world_id, live_config, world_database, tmp_path) as (port, log_path):
        # Clients title themselves from this; it must be the package's name, not a default.
        announced = _get(f"http://127.0.0.1:{port}/play/world")
        assert (announced["id"], announced["name"]) == (world_id, world.manifest.world.name)
        assert announced["theme"]["mark"], announced
        back = OPPOSITE.get(direction, direction)
        text = "\n".join(
            asyncio.run(_play(port, ["say smoke test", direction, back, "who", "quit"]))
        )

    server_log = log_path.read_text("utf-8", errors="replace")
    print(f"--- {world_id} transcript ---\n{text}")  # shown with -s or on failure
    assert f"World: {world_id}" in server_log
    assert f"[ {world.start_room} ]" in text, text
    assert f"[ {destination} ]" in text, text
    assert 'You say: "smoke test"' in text, text
    assert "Goodbye" in text, text
    assert "[" + "missing" not in text
    assert _unresolved_keys(text) == [], f"unresolved lexicon keys: {_unresolved_keys(text)}"
    assert "Traceback" not in server_log, server_log[-4000:]


@pytest.mark.parametrize("world_id", ["rivermoot"])
def test_second_world_plays_its_loop(world_id, live_config, world_database, tmp_path):
    """Rivermoot on ten first-party plugins: silver shop, hand slot, a kill, a level's experience,
    food, and rest only where the world allows it."""
    script = [
        "north",  # bridge -> market (shop, river rat)
        "browse",
        "buy bread",
        "buy cudgel",
        "equip cudgel",
        "wallet",
        "#wait 6",  # the market's rat spawns on the next spawner pass
        "attack rat",
        "#wait 6",
        "attack rat",
        "level",
        "rest",  # refused: the market is no shrine or inn
        "east",  # -> shrine
        "use bread",
        "quit",
    ]
    with _running_world(world_id, live_config, world_database, tmp_path) as (port, log_path):
        text = "\n".join(asyncio.run(_play(port, script)))
    server_log = log_path.read_text("utf-8", errors="replace")
    print(f"--- {world_id} loop transcript ---\n{text}")
    assert "the market stalls" in text, text
    assert "You buy the loaf of bread for 1 silver (9 left)." in text, text
    assert "You buy the oak cudgel for 6 silver (3 left)." in text, text
    assert "You ready the oak cudgel (hand)." in text, text
    assert "You carry 3 silver." in text, text
    assert "You gain 5 experience." in text, text
    # One or two rats, depending on the spawner pass; ten experience is level 2 in Rivermoot.
    assert "Level 1  (5/10 experience)" in text or "Level 2  (0/20 experience)" in text, text
    assert "Too dangerous to rest here." in text, text
    assert "[ town:shrine ]" in text, text
    # Eaten if a rat bit back, kept if still at full health (consumables refuse a +0 meal).
    assert "You consume the loaf of bread" in text or "you keep the loaf of bread" in text, text
    assert _unresolved_keys(text) == [], f"unresolved lexicon keys: {_unresolved_keys(text)}"
    assert "Traceback" not in server_log, server_log[-4000:]
