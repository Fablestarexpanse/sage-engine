"""`sage quickstart` config generation and refusals (no services needed)."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from sage import quickstart
from sage.quickstart import QuickstartError, database_for, ensure_config

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("server.example.toml", "database.example.toml"):
        shutil.copy(REPO / "config" / name, tmp_path / "config" / name)
    (tmp_path / "worlds" / "demo").mkdir(parents=True)
    (tmp_path / "worlds" / "demo" / "world.toml").write_text("[world]\nid = 'demo'\n")
    return tmp_path


def _toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _env(path: Path) -> dict[str, str]:
    return quickstart._read_env(path)


def test_fresh_checkout_gets_matching_config_with_secrets(root: Path):
    result = ensure_config(root, "demo")
    assert result.written == [".env", "config/server.toml", "config/database.toml"]
    server = _toml(root / "config" / "server.toml")
    database = _toml(root / "config" / "database.toml")
    password = _env(root / ".env")["POSTGRES_PASSWORD"]
    assert len(password) >= 24
    assert database["password"] == password
    assert database["database"] == "sage_demo"
    assert server["world"] == "demo"
    assert server["dev_mode"] is True
    assert len(server["admin_jwt_secret"]) == 64
    assert server["admin_auth_required"] is True


def test_second_run_changes_nothing(root: Path):
    ensure_config(root, "demo")
    before = {p: p.read_bytes() for p in (root / ".env", *(root / "config").glob("*.toml"))}
    result = ensure_config(root, "rivermoot")
    assert result.written == []
    assert {p: p.read_bytes() for p in before} == before


def test_existing_env_password_and_user_are_used(root: Path):
    (root / ".env").write_text("POSTGRES_PASSWORD=from-env\nPOSTGRES_USER=olduser\n")
    result = ensure_config(root, "demo")
    assert ".env" in result.kept
    database = _toml(root / "config" / "database.toml")
    assert (database["password"], database["user"]) == ("from-env", "olduser")


def test_existing_database_password_is_copied_into_env(root: Path):
    (root / "config" / "database.toml").write_text('password = "kept-password"\n')
    ensure_config(root, "demo")
    assert _env(root / ".env")["POSTGRES_PASSWORD"] == "kept-password"


def test_other_worlds_get_their_own_database():
    assert database_for("demo", "demo", "my_db") == "my_db"
    assert database_for("rivermoot", "demo", "my_db") == "sage_rivermoot"


def test_refuses_bad_world_id_and_missing_package(root: Path):
    with pytest.raises(QuickstartError, match="lowercase"):
        quickstart.run("Bad World", root=root, docker=False, server=False, say=lambda *_: None)
    with pytest.raises(QuickstartError, match="no world package at worlds/nowhere"):
        quickstart.run("nowhere", root=root, docker=False, server=False, say=lambda *_: None)
    assert not (root / ".env").exists()


def test_missing_docker_says_what_to_do(root: Path, monkeypatch):
    monkeypatch.setattr(quickstart.shutil, "which", lambda _name: None)
    with pytest.raises(QuickstartError, match="--no-docker"):
        quickstart.docker_up(root)


def _client_tree(root: Path, built: bool) -> Path:
    client = root / quickstart.CLIENT
    (client / "src").mkdir(parents=True)
    (client / "src" / "App.jsx").write_text("export default 1")
    if built:
        (client / "dist").mkdir()
        (client / "dist" / "index.html").write_text("<html></html>")
    return client


def test_client_build_is_stale_until_built_and_again_after_a_source_change(root: Path):
    import os
    import time

    client = _client_tree(root, built=False)
    assert quickstart.client_build_stale(client)
    (client / "dist").mkdir()
    (client / "dist" / "index.html").write_text("<html></html>")
    past = time.time() - 60
    os.utime(client / "src" / "App.jsx", (past, past))
    assert not quickstart.client_build_stale(client)
    assert quickstart.build_client(root, say=lambda *_: None) == "current"
    (client / "src" / "App.jsx").write_text("export default 2")
    future = time.time() + 60
    os.utime(client / "src" / "App.jsx", (future, future))
    assert quickstart.client_build_stale(client)


def test_missing_node_skips_the_client_but_not_the_server(root: Path, monkeypatch):
    _client_tree(root, built=False)
    monkeypatch.setattr(quickstart.shutil, "which", lambda _name: None)
    notes: list[str] = []
    assert quickstart.build_client(root, say=notes.append) == "skipped"
    assert "install Node.js" in notes[0]
