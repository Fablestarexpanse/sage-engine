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


# ---- player-account moderation endpoints -----------------------------------


def test_account_patch_requires_players_tool(client, server):
    # staff 2 has only "dashboard"
    r = client.patch("/admin/player-accounts/1", json={"is_gm": True}, headers=_auth(server, 2))
    assert r.status_code == 403


def test_console_access_grant_requires_head_or_admin_role(client, server, monkeypatch):
    # staff 2 is a gm; give them the players tool so only the role gate can reject
    rows = {(AdminStaff, 2): _staff_row(2, role="gm", tools=["players", "dashboard"])}
    monkeypatch.setattr(server.db, "session_factory", lambda: _FakeSession(rows))
    r = client.put(
        "/admin/player-accounts/1/console-access",
        json={"password": "longenough1", "role": "gm"},
        headers=_auth(server, 2),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "head_or_admin_required"


def test_account_patch_missing_account_404(client, server, monkeypatch):
    from fablestar.admin.routes import admin_ops as admin_ops_mod

    async def _none(*a, **k):
        return None

    monkeypatch.setattr(admin_ops_mod.player_accounts, "patch_account", _none)
    r = client.patch("/admin/player-accounts/999", json={"is_gm": True}, headers=_auth(server, 1))
    assert r.status_code == 404
    assert r.json()["detail"] == "account_not_found"


def test_account_patch_passes_patch_and_actor(client, server, monkeypatch):
    from fablestar.admin.routes import admin_ops as admin_ops_mod

    captured = {}

    async def _patch_account(srv, account_id, patch, actor=None):
        captured.update({"account_id": account_id, "patch": patch, "actor": actor})
        return {"id": account_id, **patch}

    monkeypatch.setattr(admin_ops_mod.player_accounts, "patch_account", _patch_account)
    r = client.patch("/admin/player-accounts/7", json={"is_gm": True}, headers=_auth(server, 1))
    assert r.status_code == 200
    assert captured["account_id"] == 7
    assert captured["patch"] == {"is_gm": True}
    assert captured["actor"]["username"] == "staff1"


def test_character_patch_missing_character_404(client, server, monkeypatch):
    from fablestar.admin.routes import admin_ops as admin_ops_mod

    async def _none(*a, **k):
        return None

    monkeypatch.setattr(admin_ops_mod.player_accounts, "patch_character", _none)
    r = client.patch(
        "/admin/player-accounts/1/characters/5",
        json={"name": "NewName"},
        headers=_auth(server, 1),
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "character_not_found"


def test_console_access_revoke_reports_missing_grant(client, server, monkeypatch):
    from fablestar.admin.routes import admin_ops as admin_ops_mod

    async def _revoke(srv, account_id):
        return False

    monkeypatch.setattr(
        admin_ops_mod.staff_service, "revoke_console_access_for_play_account", _revoke
    )
    r = client.delete("/admin/player-accounts/3/console-access", headers=_auth(server, 1))
    assert r.status_code == 404
    assert r.json()["detail"] == "console_access_not_found"


# ---- staff create / patch ---------------------------------------------------


def test_staff_create_forwards_fields_and_requires_head_admin(client, server, monkeypatch):
    from fablestar.admin.routes import admin_ops as admin_ops_mod

    captured = {}

    async def _create_staff(srv, *, username, password, display_name, role, permissions):
        captured.update(
            {
                "username": username,
                "display_name": display_name,
                "role": role,
                "permissions": permissions,
            }
        )
        return _staff_row(9, role=role)

    monkeypatch.setattr(admin_ops_mod.staff_service, "create_staff", _create_staff)
    body = {
        "username": "newgm",
        "password": "longenough1",
        "display_name": "New GM",
        "role": "gm",
        "permissions": {"tools": ["dashboard"]},
    }
    # gm caller rejected before the service is touched
    r = client.post("/admin/staff", json=body, headers=_auth(server, 2))
    assert r.status_code == 403
    assert captured == {}
    # head admin succeeds and the payload reaches the service intact
    r = client.post("/admin/staff", json=body, headers=_auth(server, 1))
    assert r.status_code == 200
    assert captured["username"] == "newgm"
    assert captured["role"] == "gm"
    assert captured["permissions"] == {"tools": ["dashboard"]}


def test_staff_patch_sends_only_set_fields(client, server, monkeypatch):
    from fablestar.admin.routes import admin_ops as admin_ops_mod

    captured = {}

    async def _apply_staff_patch(srv, staff_id, patch):
        captured.update({"staff_id": staff_id, "patch": patch})
        return _staff_row(staff_id)

    monkeypatch.setattr(admin_ops_mod.staff_service, "apply_staff_patch", _apply_staff_patch)
    r = client.patch("/admin/staff/4", json={"is_active": False}, headers=_auth(server, 1))
    assert r.status_code == 200
    assert captured["staff_id"] == 4
    # exclude_unset: untouched optional fields must not leak into the patch
    assert captured["patch"] == {"is_active": False}


def test_staff_patch_rejects_short_password(client, server):
    r = client.patch("/admin/staff/4", json={"password": "short"}, headers=_auth(server, 1))
    assert r.status_code == 422
