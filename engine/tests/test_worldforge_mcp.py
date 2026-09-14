"""worldforge-mcp validates with the engine's linter and takes room types from world.toml."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

pytest.importorskip("mcp")

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def mcp_server(tmp_path, monkeypatch):
    """The MCP module pointed at a copy of Rivermoot (world.toml next to its content)."""
    package = tmp_path / "rivermoot"
    shutil.copytree(ROOT / "worlds" / "rivermoot" / "content", package / "content")
    shutil.copy(ROOT / "worlds" / "rivermoot" / "world.toml", package / "world.toml")
    monkeypatch.setenv("WORLDFORGE_ROOT", str(package / "content" / "world"))
    spec = importlib.util.spec_from_file_location(
        "worldforge_mcp_under_test", ROOT / "engine" / "tools" / "worldforge-mcp" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, package


def test_validate_zone_is_the_engine_linter(mcp_server):
    server, package = mcp_server
    report = server.validate_zone("town")
    assert report["counts"] == {"err": 0, "warn": 0}
    assert any("dead end" in line for line in report["info"])

    market = package / "content" / "world" / "zones" / "town" / "rooms" / "market.yaml"
    market.write_text(
        market.read_text(encoding="utf-8").replace("town:shrine", "town:nowhere"), encoding="utf-8"
    )
    report = server.validate_zone("town")
    assert "town:market east: destination 'town:nowhere' does not exist" in report["errors"]


def test_room_types_come_from_world_toml(mcp_server):
    server, _ = mcp_server
    assert server._room_types()[:3] == ["street", "square", "shrine"]
    refused = server.create_room("town", "ferry_bridge", room_type="airlock", x=10, y=10)
    assert refused.startswith("ERROR: room type 'airlock'")
    server.create_room("town", "tollhouse", x=10, y=10)
    doc = (Path(server._rooms_dir("town")) / "tollhouse.yaml").read_text(encoding="utf-8")
    assert "type: street" in doc
