"""Admin HTTP surface tests — auth middleware, tool permissions, room-write 409 guard.

Runs the real NexusApp (all routers + NexusAdminAuthMiddleware) over the
in-memory fakes from tests/fakes.py via FastAPI's TestClient. No live
Redis/Postgres: DB access is a fake session_factory that serves AdminStaff
rows from a dict.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from fablestar.admin import content_browser
from fablestar.admin.admin_security import issue_staff_token
from fablestar.admin.nexus import NexusApp
from fablestar.state.models import AdminStaff
from tests.fakes import make_fake_server

SECRET = "test-secret-not-a-real-deployment-value"


class _FakeSession:
    """Async session stub: .get() serves rows from a dict keyed by (model, id)."""

    def __init__(self, rows: dict):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return self._rows.get((model, pk))


def _staff_row(staff_id: int, role: str = "head_admin", tools: list[str] | None = None):
    row = AdminStaff()
    row.id = staff_id
    row.username = f"staff{staff_id}"
    row.display_name = f"Staff {staff_id}"
    row.role = role
    row.permissions = {} if tools is None else {"tools": tools}
    row.is_active = True
    return row


@pytest.fixture()
def server():
    srv = make_fake_server()
    srv.config = SimpleNamespace(
        server=SimpleNamespace(
            proficiency_combat_hybrid=True,
            admin_auth_required=True,
            admin_jwt_secret=SECRET,
            cors_origins=[],
        ),
        comfyui=SimpleNamespace(enabled=False),
    )
    rows = {
        (AdminStaff, 1): _staff_row(1, role="head_admin"),
        (AdminStaff, 2): _staff_row(2, role="gm", tools=["dashboard"]),
    }
    srv.db = SimpleNamespace(session_factory=lambda: _FakeSession(rows))
    srv.last_content_reload_at = None
    return srv


@pytest.fixture()
def client(server):
    return TestClient(NexusApp(server).app, raise_server_exceptions=False)


def _auth(server, staff_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_staff_token(server, staff_id)}"}


# ---- auth middleware -------------------------------------------------------


def test_protected_route_requires_token(client):
    assert client.get("/admin/me").status_code == 401


def test_garbage_token_rejected(client):
    r = client.get("/admin/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_token"


def test_play_health_is_public(client):
    r = client.get("/play/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_valid_staff_token_resolves_context(client, server):
    r = client.get("/admin/me", headers=_auth(server, 1))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "head_admin"
    assert body["username"] == "staff1"


# ---- tool / role permissions ----------------------------------------------


def test_tool_denied_for_unlisted_tool(client, server):
    # staff 2 has only the "dashboard" tool; /content/entities needs "entities"
    r = client.get("/content/entities", headers=_auth(server, 2))
    assert r.status_code == 403
    assert "tool_denied" in r.json()["detail"]


def test_staff_routes_reject_non_head_admin(client, server):
    r = client.get("/admin/staff", headers=_auth(server, 2))
    assert r.status_code == 403
    assert r.json()["detail"] == "head_admin_only"


# ---- optimistic-concurrency 409 guard --------------------------------------


def test_room_save_conflict_returns_409(client, server, monkeypatch):
    monkeypatch.setattr(content_browser, "room_file_mtime", lambda z, r: 2000.0)
    r = client.put(
        "/content/room/somezone/someroom/yaml",
        json={"path": "x", "yaml_content": "id: somezone:someroom", "expected_mtime": 1000.0},
        headers=_auth(server, 1),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "content_modified"


def test_room_delete_conflict_returns_409(client, server, monkeypatch):
    monkeypatch.setattr(content_browser, "room_file_mtime", lambda z, r: 2000.0)
    r = client.delete(
        "/content/zones/somezone/rooms/someroom",
        params={"expected_mtime": 1000.0},
        headers=_auth(server, 1),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "content_modified"
