"""AI art credit bundles are deployment config (comfyui.toml), served to the admin console."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from sage.core.comfyui_persist import save_comfyui_toml
from sage.core.config import ComfyUIConfig, CreditBundle, load_config


def test_bundles_load_from_toml_and_survive_an_admin_save(tmp_path):
    (tmp_path / "comfyui.toml").write_text(
        'credits_per_usd = 120\n\n[[credit_bundles]]\nid = "river"\nlabel = "5 silver pieces"\n'
        'credits = 300\nblurb = "a test pack"\n',
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path)).comfyui
    assert cfg.credit_bundles == [
        CreditBundle(id="river", label="5 silver pieces", credits=300, blurb="a test pack")
    ]

    save_comfyui_toml(cfg, tmp_path / "comfyui.toml")
    again = load_config(str(tmp_path)).comfyui
    assert again.credit_bundles == cfg.credit_bundles and again.credits_per_usd == 120
    assert ComfyUIConfig().credit_bundles == []  # no pricing unless a deployment sets it


def test_admin_economy_route_serves_the_bundles():
    from sage.admin.nexus import NexusApp
    from tests.fakes import make_fake_server

    server = make_fake_server()
    server.config = SimpleNamespace(
        server=SimpleNamespace(admin_auth_required=False, admin_jwt_secret="x", cors_origins=[]),
        comfyui=ComfyUIConfig(credit_bundles=[CreditBundle(id="a", label="$1", credits=100)]),
    )
    server.last_content_reload_at = None
    body = TestClient(NexusApp(server).app).get("/admin/economy").json()
    assert body["credit_bundles"] == [{"id": "a", "label": "$1", "credits": 100, "blurb": ""}]
    assert body["credits_per_usd"] == 100
