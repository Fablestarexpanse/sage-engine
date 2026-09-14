# DEV-AUTH:FILE — tests for development-only passwordless logins; stripped for release.
"""Passwordless dev logins exist only with both dev flags, and only for direct loopback clients."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sage.admin.nexus import NexusApp
from sage.admin.routes.dev_auth import dev_auth_enabled
from sage.core.config import ServerConfig
from tests.fakes import make_fake_server

LOCAL = ("127.0.0.1", 50000)
ROUTES = ("/play/dev/status", "/admin/dev/status")


def _server(dev_mode: bool, dev_login: bool):
    srv = make_fake_server()
    srv.config = SimpleNamespace(
        server=SimpleNamespace(
            admin_auth_required=True,
            admin_jwt_secret="test-secret-not-a-real-deployment-value",
            cors_origins=[],
            dev_mode=dev_mode,
            dev_login=dev_login,
        ),
        comfyui=SimpleNamespace(enabled=False),
    )
    srv.last_content_reload_at = None
    return srv


def test_dev_login_needs_both_flags_and_defaults_off():
    assert ServerConfig().dev_login is False
    for mode, login, on in (
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, True),
    ):
        assert dev_auth_enabled(_server(mode, login)) is on, (mode, login)


@pytest.mark.parametrize("flags", [(False, False), (True, False), (False, True)])
def test_routes_do_not_exist_without_both_flags(flags):
    client = TestClient(NexusApp(_server(*flags)).app, client=LOCAL, raise_server_exceptions=False)
    assert client.post("/play/dev/login", json={"character": "Qa Tester"}).status_code == 404
    # Admin paths without the route fall to the auth middleware: no token, no entry.
    assert client.post("/admin/dev/login").status_code in (401, 404)
    assert client.get("/play/dev/status").status_code == 404


def test_loopback_client_sees_dev_login_without_a_token():
    client = TestClient(NexusApp(_server(True, True)).app, client=LOCAL)
    for path in ROUTES:
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.json() == {"enabled": True}


def test_remote_client_is_refused():
    client = TestClient(NexusApp(_server(True, True)).app, client=("192.168.1.20", 50000))
    for path in ROUTES:
        assert client.get(path).json() == {"enabled": False}
    assert client.post("/play/dev/login", json={}).status_code == 404
    assert client.post("/admin/dev/login").status_code == 404


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Forwarded-For": "192.168.1.20"},
        # A spoofed loopback entry, then the address the proxy saw.
        {"X-Forwarded-For": "127.0.0.1, 192.168.1.20"},
        {"X-Real-IP": "203.0.113.9"},
        {"Forwarded": 'for="[2001:db8::1]:4711"'},
        {"Forwarded": "proto=http"},  # relayed, but for whom is not said
    ],
)
def test_request_relayed_for_a_network_client_is_refused(headers):
    client = TestClient(NexusApp(_server(True, True)).app, client=LOCAL)
    assert client.get("/play/dev/status", headers=headers).json() == {"enabled": False}
    assert client.post("/play/dev/login", json={}, headers=headers).status_code == 404
    assert client.post("/admin/dev/login", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Forwarded-For": "::1"},  # the Vite dev proxy relaying a browser on this machine
        {"X-Forwarded-For": "::ffff:127.0.0.1", "X-Forwarded-Host": "localhost:5174"},
        {"Forwarded": "for=127.0.0.1;proto=http"},
    ],
)
def test_request_relayed_for_a_browser_on_this_machine_is_local(headers):
    client = TestClient(NexusApp(_server(True, True)).app, client=LOCAL)
    for path in ROUTES:
        assert client.get(path, headers=headers).json() == {"enabled": True}, path
