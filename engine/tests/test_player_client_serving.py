"""Nexus serves the built player client at / without shadowing or unguarding any API route."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sage.admin.nexus import NexusApp
from sage.admin.player_client import client_file, is_client_path
from tests.fakes import make_fake_server


@pytest.fixture()
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>player client</html>")
    (root / "assets" / "app-123.js").write_text("console.log('app')")
    (root / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside the build")
    return root


def _client(dist_dir):
    srv = make_fake_server()
    srv.config = SimpleNamespace(
        server=SimpleNamespace(
            admin_auth_required=True,
            admin_jwt_secret="test-secret-not-a-real-deployment-value",
            cors_origins=[],
            player_client_dir=str(dist_dir),
        ),
        comfyui=SimpleNamespace(enabled=False),
    )
    srv.last_content_reload_at = None
    nexus = NexusApp(srv)
    return nexus, TestClient(nexus.app, raise_server_exceptions=False)


def test_index_assets_and_root_files_are_served(dist):
    _, client = _client(dist)
    index = client.get("/")
    assert index.status_code == 200 and "player client" in index.text
    assert index.headers["cache-control"] == "no-cache"
    assert client.get("/assets/app-123.js").text == "console.log('app')"
    assert client.get("/favicon.svg").status_code == 200


def test_api_routes_keep_their_auth_and_their_404s(dist):
    _, client = _client(dist)
    assert client.get("/admin/staff").status_code == 401
    assert client.get("/play/health").status_code == 200
    missing = client.get("/assets/nope.js")
    assert missing.status_code == 404 and missing.json() == {"detail": "Not Found"}
    assert client.post("/").status_code in (404, 405)


def test_routes_added_later_are_not_shadowed(dist):
    nexus, client = _client(dist)

    @nexus.app.get("/late.json")
    async def late():
        return {"route": "late"}

    assert client.get("/late.json").json() == {"route": "late"}


def test_no_build_means_plain_404(tmp_path):
    _, client = _client(tmp_path / "not-built")
    assert client.get("/").status_code == 404


def test_files_outside_the_build_are_never_served(dist):
    assert client_file(dist, "/../secret.txt") is None
    assert client_file(dist, "/assets/../../secret.txt") is None
    assert client_file(dist, "/index.html") is not None


@pytest.mark.parametrize(
    "path, owned",
    [
        ("/", True),
        ("/assets/a.js", True),
        ("/favicon.svg", True),
        ("/play/health", False),
        ("/admin/staff", False),
        ("/status", False),
    ],
)
def test_client_paths(path, owned):
    assert is_client_path(path) is owned
