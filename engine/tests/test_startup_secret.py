"""The server refuses to start without a JWT secret when admin auth is on.

Before, it started and reported healthy, and the first registration or login returned HTTP 500
(measured in docs/sage/ONBOARDING_PLAN.md section 2).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest import mock

import pytest

from sage.core.config import LEGACY_ENV_PREFIX
from sage.server import SageServer


def _server(secret: str | None, auth_required: bool = True):
    connected = []

    async def connect():
        connected.append(True)
        raise AssertionError("startup reached Redis")

    manifest = SimpleNamespace(id="demo", name="Demo", version="0.1.0")
    return SimpleNamespace(
        world=SimpleNamespace(manifest=SimpleNamespace(world=manifest), root="worlds/demo"),
        config=SimpleNamespace(
            server=SimpleNamespace(admin_jwt_secret=secret, admin_auth_required=auth_required)
        ),
        redis=SimpleNamespace(connect=connect),
    ), connected


@pytest.fixture(autouse=True)
def _no_env_secret():
    blank = {"SAGE_ADMIN_JWT_SECRET": "", f"{LEGACY_ENV_PREFIX}ADMIN_JWT_SECRET": ""}
    with mock.patch.dict("os.environ", blank):
        yield


def test_startup_refuses_before_touching_services_without_a_secret():
    server, connected = _server(None)
    with pytest.raises(RuntimeError, match="no JWT secret is configured"):
        asyncio.run(SageServer.startup(server))
    assert connected == []


@pytest.mark.parametrize("secret, auth_required", [("a" * 64, True), (None, False)])
def test_startup_continues_with_a_secret_or_without_admin_auth(secret, auth_required):
    server, connected = _server(secret, auth_required)
    with pytest.raises(AssertionError, match="startup reached Redis"):
        asyncio.run(SageServer.startup(server))
    assert connected == [True]
