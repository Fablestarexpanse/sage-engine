"""Admin HTTP surface tests — auth middleware, tool permissions, staff and lexicon routes.

Runs the real NexusApp (all routers + NexusAdminAuthMiddleware) over the
in-memory fakes from tests/fakes.py via FastAPI's TestClient. No live
Redis/Postgres: DB access is a fake session_factory that serves AdminStaff
rows from a dict.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sage.admin.admin_security import issue_staff_token
from sage.admin.nexus import NexusApp
from sage.state.models import AdminStaff
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


def test_plugin_pages_list_mounted_admin_tools_the_staff_may_use(client, server):
    server.plugins = SimpleNamespace(admin_tools=[("skilltree", "skills"), ("roster", "agents")])
    r = client.get("/admin/plugin-pages", headers=_auth(server, 1))
    assert r.status_code == 200
    assert r.json() == [
        {"plugin": "skilltree", "tool": "skills", "base": "/plugins/skilltree/admin"},
        {"plugin": "roster", "tool": "agents", "base": "/plugins/roster/admin"},
    ]
    assert client.get("/admin/plugin-pages", headers=_auth(server, 2)).json() == []
    server.plugins = SimpleNamespace(admin_tools=[])
    assert client.get("/admin/plugin-pages", headers=_auth(server, 1)).json() == []


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


def test_play_commands_lists_the_registry(client):
    from sage.commands.registry import registry

    async def handler(session, args):
        return None

    registry.register("zzprobe", handler, aliases=["zzp"])
    try:
        r = client.get("/play/commands")
        assert r.status_code == 200
        names = r.json()["commands"]
        assert "zzprobe" in names and "zzp" not in names
        assert names == sorted(names)
    finally:
        registry._commands.pop("zzprobe", None)
        registry._aliases.pop("zzp", None)


def test_play_world_names_the_running_world(client, server):
    r = client.get("/play/world")
    assert r.status_code == 200
    body = r.json()
    assert (body["id"], body["name"]) == (server.world.id, server.world.manifest.world.name)
    assert set(body["theme"]) <= {"mark", "accent"}


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
    from sage.admin.routes import admin_ops as admin_ops_mod

    async def _none(*a, **k):
        return None

    monkeypatch.setattr(admin_ops_mod.player_accounts, "patch_account", _none)
    r = client.patch("/admin/player-accounts/999", json={"is_gm": True}, headers=_auth(server, 1))
    assert r.status_code == 404
    assert r.json()["detail"] == "account_not_found"


def test_account_patch_passes_patch_and_actor(client, server, monkeypatch):
    from sage.admin.routes import admin_ops as admin_ops_mod

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
    from sage.admin.routes import admin_ops as admin_ops_mod

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
    from sage.admin.routes import admin_ops as admin_ops_mod

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
    from sage.admin.routes import admin_ops as admin_ops_mod

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
    from sage.admin.routes import admin_ops as admin_ops_mod

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


# ---- lexicon editing (decision 7) ------------------------------------------


class _FakeOverrides:
    def __init__(self):
        self.rows: dict[str, list[dict]] = {}

    async def active(self):
        return {
            k: next(v["value"] for v in vs if v["active"])
            for k, vs in self.rows.items()
            if any(v["active"] for v in vs)
        }

    async def history(self, key):
        return list(reversed(self.rows.get(key, [])))

    async def save(self, key, value, author_staff_id, note=None):
        versions = self.rows.setdefault(key, [])
        for v in versions:
            v["active"] = False
        versions.append(
            {"version": len(versions) + 1, "value": value, "active": True, "note": note}
        )
        return len(versions)

    async def rollback(self, key, version):
        from sage.lexicon.overrides import OverrideError

        versions = self.rows.get(key, [])
        if not any(v["version"] == version for v in versions):
            raise OverrideError(f"{key!r} has no version {version}")
        for v in versions:
            v["active"] = v["version"] == version

    async def clear(self, key):
        for v in self.rows.get(key, []):
            v["active"] = False


@pytest.fixture()
def lexicon_client(server):
    from sage.lexicon import Lexicon

    base = [
        ("world", {"login.motd": "Mind the eels."}),
        ("engine", {"prompt": "> ", "login.motd": ""}),
    ]
    server.world = SimpleNamespace(id="demo")
    server.lexicon_overrides = _FakeOverrides()
    server.lexicon = Lexicon(base)

    async def reload_lexicon_overrides():
        active = await server.lexicon_overrides.active()
        server.lexicon = Lexicon([("override", active), *base] if active else base)

    server.reload_lexicon_overrides = reload_lexicon_overrides
    return TestClient(NexusApp(server).app, raise_server_exceptions=False)


def test_lexicon_requires_the_lexicon_tool(lexicon_client, server):
    assert lexicon_client.get("/admin/lexicon", headers=_auth(server, 2)).status_code == 403


def test_lexicon_edit_rollback_and_revert(lexicon_client, server):
    head = _auth(server, 1)
    listing = lexicon_client.get("/admin/lexicon", headers=head).json()
    motd = next(r for r in listing["keys"] if r["key"] == "login.motd")
    assert (motd["value"], motd["source"], motd["overridden"]) == ("Mind the eels.", "world", False)

    r = lexicon_client.put(
        "/admin/lexicon/login.motd", json={"value": "Flood warning!"}, headers=head
    )
    assert r.status_code == 200 and r.json() == {
        "key": "login.motd",
        "version": 1,
        "value": "Flood warning!",
    }
    lexicon_client.put("/admin/lexicon/login.motd", json={"value": "All clear."}, headers=head)
    assert server.lexicon.get("login.motd") == "All clear."

    r = lexicon_client.post("/admin/lexicon/login.motd/rollback", json={"version": 1}, headers=head)
    assert r.json()["value"] == "Flood warning!"
    history = lexicon_client.get("/admin/lexicon/login.motd/history", headers=head).json()[
        "versions"
    ]
    assert [(v["version"], v["active"]) for v in history] == [(2, False), (1, True)]

    r = lexicon_client.delete("/admin/lexicon/login.motd", headers=head)
    assert r.json() == {"key": "login.motd", "value": "Mind the eels.", "source": "world"}


def test_lexicon_rejects_unknown_keys_and_versions(lexicon_client, server):
    head = _auth(server, 1)
    assert (
        lexicon_client.put(
            "/admin/lexicon/no.such.key", json={"value": "x"}, headers=head
        ).status_code
        == 404
    )
    assert (
        lexicon_client.post(
            "/admin/lexicon/prompt/rollback", json={"version": 9}, headers=head
        ).status_code
        == 404
    )
