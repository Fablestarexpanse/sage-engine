"""Content schema: engine models plus plugin extension fields, and each package's exported copy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sage.plugins.offline import registration_host
from sage.world.package import available_worlds, load_world_package
from sage.world.schema import SCHEMA_FILE, content_schema, dumps

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("world_id", available_worlds(ROOT / "worlds"))
def test_exported_schema_is_current(world_id):
    world = load_world_package(ROOT / "worlds" / world_id)
    with registration_host(world, ROOT) as host:
        text = dumps(content_schema(world, host.extensions))
    exported = world.root / SCHEMA_FILE
    assert exported.is_file(), (
        f"run: python -m sage schema export --world {world_id} --out {exported}"
    )
    assert exported.read_text(encoding="utf-8") == text, (
        f"{exported} is stale; run: python -m sage schema export --world {world_id} --out {exported}"
    )


def test_schema_carries_world_lists_and_plugin_fields():
    world = load_world_package(ROOT / "worlds" / "rivermoot")
    schema = json.loads((world.root / SCHEMA_FILE).read_text(encoding="utf-8"))
    assert schema["content"]["equipment_slots"] == ["hand", "body"]
    assert "inn" in schema["content"]["room_types"]
    assert [a["key"] for a in schema["attributes"]] == ["mgt", "wts", "nrv"]
    assert [c["key"] for c in schema["currencies"]] == ["silver"]
    shop = schema["extensions"]["room.shop"]
    assert shop["owner"] == "shop" and "sells" in shop["schema"]["properties"]
    assert schema["extensions"]["feature.search"]["owner"] == "search"
    assert "item.recipe" not in schema["extensions"]  # crafting is not enabled in Rivermoot
    assert set(schema["models"]) == {"room", "feature", "entity", "item", "zone"}


def test_schema_route_serves_the_running_world(monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from sage.admin.nexus import NexusApp
    from sage.world.extensions import ContentExtensions
    from tests.fakes import make_fake_server

    server = make_fake_server()
    server.config = SimpleNamespace(
        server=SimpleNamespace(admin_auth_required=False, admin_jwt_secret="x", cors_origins=[]),
        comfyui=SimpleNamespace(enabled=False),
    )
    server.last_content_reload_at = None
    server.plugins = SimpleNamespace(extensions=ContentExtensions(), admin_tools=[])
    body = TestClient(NexusApp(server).app).get("/schema/world").json()
    assert body["world"]["id"] == server.world.id
    assert body["extensions"] == {}
