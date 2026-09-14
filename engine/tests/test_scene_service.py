"""SceneService — validation branches, URL safety, and gallery apply ownership.

Covers the pre-ComfyUI logic (auth, prompt bounds, not-configured early exit)
and apply_scene_from_gallery's ownership/URL checks with scripted fakes; the
actual ComfyUI HTTP round-trip stays out of scope for the default suite.
"""

import asyncio
from types import SimpleNamespace

from sage.services.scene_service import SceneService, _is_safe_player_scene_storage_url
from sage.state.models import Account, AccountSceneImage, Character
from tests.fakes import fake_wallet

# ---- storage-URL guard ------------------------------------------------------


def test_storage_url_guard_accepts_media_rooms_only():
    assert _is_safe_player_scene_storage_url("/media/rooms/x.png")
    assert _is_safe_player_scene_storage_url("/media/room-art/zone/slug.png")
    assert not _is_safe_player_scene_storage_url("/media/portraits/x.png")
    assert not _is_safe_player_scene_storage_url("/media/rooms/../../etc/passwd")
    assert not _is_safe_player_scene_storage_url("https://evil.example/x.png")
    assert not _is_safe_player_scene_storage_url("")


# ---- generate_scene_image early exits ---------------------------------------


class _GallerySession:
    """get() answers per (model): {Account: ..., AccountSceneImage: ..., Character: ...}"""

    def __init__(self, rows):
        self._rows = rows
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return self._rows.get(model)

    async def execute(self, stmt):  # resolve_play_account credential path (unused: token path)
        raise AssertionError("unexpected execute")

    async def commit(self):
        self.committed = True


def _account(aid=5):
    a = Account()
    a.id = aid
    a.username = "player"
    a.ai_credits = 100
    return a


def _scene_server(rows, comfy_enabled=False):
    session = _GallerySession(rows)

    async def fake_resolve(db_session, server, **kw):
        return rows.get(Account)

    srv = SimpleNamespace(
        db=SimpleNamespace(session_factory=lambda: session),
        config=SimpleNamespace(
            comfyui=SimpleNamespace(
                enabled=comfy_enabled,
                workflow_path="does-not-exist.json",
                area_workflow_path="",
                area_generation_cost=10,
                currency_display_name="credits",
                credits_per_usd=100,
                economy_enabled=True,
            ),
        ),
        wallet=fake_wallet(),
    )
    return srv, session, fake_resolve


async def _fake_resolve_or_error(server, **kw):
    return _account(), None


def test_generate_scene_image_prompt_bounds(monkeypatch):
    async def check():
        srv, _, _ = _scene_server({Account: _account()})
        import sage.services.scene_service as mod

        monkeypatch.setattr(mod, "resolve_play_account_or_error", _fake_resolve_or_error)
        svc = SceneService(srv)
        r = await svc.generate_scene_image("player", "pw", "ab")
        assert r == {"ok": False, "error": "prompt_too_short"}
        r = await svc.generate_scene_image("player", "pw", "x" * 4001)
        assert r == {"ok": False, "error": "prompt_too_long"}

    asyncio.run(check())


def test_generate_scene_image_not_configured_reports_balance(monkeypatch):
    async def check():
        srv, _, _ = _scene_server({Account: _account()}, comfy_enabled=False)
        import sage.services.scene_service as mod

        monkeypatch.setattr(mod, "resolve_play_account_or_error", _fake_resolve_or_error)

        async def read_balance(aid):
            return 77

        srv.economy = SimpleNamespace(
            public_fields=lambda: {"currency_display_name": "credits"},
            read_balance=read_balance,
        )
        r = await SceneService(srv).generate_scene_image("player", "pw", "a good prompt")
        assert r["error"] == "comfyui_not_configured"
        assert r["ai_credits"] == 77

    asyncio.run(check())


# ---- apply_scene_from_gallery ownership / URL checks ------------------------


def _gallery_row(aid=5, url="/media/rooms/scene.png"):
    row = AccountSceneImage(account_id=aid, image_url=url)
    return row


def _char(aid=5):
    c = Character()
    c.id = 9
    c.account_id = aid
    c.name = "Hero"
    return c


def _apply(monkeypatch, rows):
    srv, session, fake_resolve = _scene_server(rows)
    import sage.services.scene_service as mod

    monkeypatch.setattr(mod, "resolve_play_account", fake_resolve)

    async def run():
        return await SceneService(srv).apply_scene_from_gallery("player", "pw", 1, 9), session

    return asyncio.run(run())


def test_apply_gallery_success(monkeypatch):
    r, session = _apply(
        monkeypatch, {Account: _account(), AccountSceneImage: _gallery_row(), Character: _char()}
    )
    assert r == {"ok": True, "scene_image_url": "/media/rooms/scene.png"}
    assert session.committed


def test_apply_gallery_rejects_foreign_row(monkeypatch):
    r, _ = _apply(
        monkeypatch,
        {Account: _account(), AccountSceneImage: _gallery_row(aid=42), Character: _char()},
    )
    assert r == {"ok": False, "error": "gallery_item_not_found"}


def test_apply_gallery_rejects_unsafe_stored_url(monkeypatch):
    r, _ = _apply(
        monkeypatch,
        {
            Account: _account(),
            AccountSceneImage: _gallery_row(url="https://evil.example/x.png"),
            Character: _char(),
        },
    )
    assert r == {"ok": False, "error": "invalid_stored_url"}


def test_apply_gallery_rejects_foreign_character(monkeypatch):
    r, _ = _apply(
        monkeypatch,
        {Account: _account(), AccountSceneImage: _gallery_row(), Character: _char(aid=42)},
    )
    assert r == {"ok": False, "error": "character_not_owned"}


def test_apply_gallery_invalid_ids():
    async def check():
        srv, _, _ = _scene_server({})
        r = await SceneService(srv).apply_scene_from_gallery("player", "pw", 0, 9)
        assert r == {"ok": False, "error": "invalid_ids"}

    asyncio.run(check())
