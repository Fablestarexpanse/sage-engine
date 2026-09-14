"""GET /admin/world: the running world, loaded plugins, AI slots and online counts for the console."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from sage.admin.admin_security import issue_staff_token
from sage.admin.nexus import NexusApp
from sage.admin.routes.about import world_summary
from sage.llm.prompts import PromptManager
from sage.world.package import load_world_package
from tests.fakes import ROOT, make_fake_server


def _server(host, world):
    srv = make_fake_server()
    srv.world = world
    srv.plugins = host
    srv.prompt_manager = PromptManager(world.prompts_dir, world.style_path)
    srv.session_manager = SimpleNamespace(
        sessions={
            "a": SimpleNamespace(virtual=False),
            "b": SimpleNamespace(virtual=True),
            "c": SimpleNamespace(virtual=True),
        },
        player_to_session={},
        get_session_by_player=lambda pid: None,
    )
    srv.config = SimpleNamespace(
        server=SimpleNamespace(
            admin_auth_required=True,
            admin_jwt_secret="test-secret-not-a-real-deployment-value",
            cors_origins=[],
            dev_mode=True,
            dev_login=False,
        ),
        comfyui=SimpleNamespace(enabled=False),
    )
    srv.last_content_reload_at = None
    return srv


def test_summary_names_the_world_its_plugins_and_splits_agents_from_players(plugin_host):
    world = load_world_package(ROOT / "worlds" / "rivermoot")
    host = plugin_host(world, ["consumables"])
    summary = world_summary(_server(host, world))

    assert summary["world"]["id"] == "rivermoot"
    assert summary["world"]["name"] == world.manifest.world.name
    assert summary["world"]["path"] == "worlds/rivermoot"
    assert summary["engine"]["version"]
    [plugin] = summary["plugins"]
    assert (plugin["id"], plugin["first_party"], plugin["path"]) == (
        "consumables",
        True,
        "plugins/consumables",
    )
    assert plugin["registered"]["commands"] == ["use"]
    assert plugin["source"] == "shared"
    levels = world_summary(_server(plugin_host(world, ["levels"]), world))["plugins"][0]
    assert (levels["id"], levels["source"]) == ("levels", "world")
    assert summary["online"] == {"players": 1, "agents": 2}
    # Rivermoot narrates rooms but ships no Forge templates.
    assert summary["ai_slots"]["narrate.room"]["enabled"] is True
    assert summary["ai_slots"]["forge.room"]["enabled"] is False


def test_route_needs_a_staff_token(plugin_host):
    world = load_world_package(ROOT / "worlds" / "rivermoot")
    srv = _server(plugin_host(world, ["consumables"]), world)
    srv.db = None
    client = TestClient(NexusApp(srv).app)
    assert client.get("/admin/world").status_code == 401
    token = issue_staff_token(srv, 1)
    srv.db = SimpleNamespace(session_factory=lambda: _Staff())
    ok = client.get("/admin/world", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and ok.json()["world"]["id"] == "rivermoot"


class _Staff:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        row = model()
        row.id, row.username, row.display_name = pk, "head", "Head"
        row.role, row.permissions, row.is_active = "head_admin", {}, True
        return row
