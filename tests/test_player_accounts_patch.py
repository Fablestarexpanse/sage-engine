"""player_accounts.patch_account / patch_character — direct service tests.

The HTTP tests monkeypatch these functions out; here their real branches run
against a scripted fake session: balance clamping, echo-credit delta wording,
ownership checks, and which audit notification fires for whom.
"""

import asyncio
from types import SimpleNamespace

from sage.admin import player_accounts
from sage.state.models import Account, Character


class _FakeSession:
    def __init__(self, get_row=None, scalar_value=0):
        self._get_row = get_row
        self._scalar_value = scalar_value
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return self._get_row

    async def scalar(self, stmt):
        return self._scalar_value

    async def commit(self):
        self.committed = True

    async def refresh(self, row):
        pass


def _server(session):
    calls = {"audit": [], "grant": []}

    async def notify_audit(account_id, **kw):
        calls["audit"].append((account_id, kw))

    async def notify_grant(account_id, **kw):
        calls["grant"].append((account_id, kw))

    srv = SimpleNamespace(
        db=SimpleNamespace(session_factory=lambda: session),
        config=SimpleNamespace(comfyui=SimpleNamespace(currency_display_name="pixels")),
        notify_play_clients_staff_audit=notify_audit,
        notify_play_clients_echo_grant=notify_grant,
    )
    return srv, calls


def _account(credits=50, is_gm=False):
    a = Account()
    a.id = 7
    a.username = "player"
    a.email = None
    a.echo_credits = credits
    a.is_gm = is_gm
    return a


def _character(account_id=7):
    c = Character()
    c.id = 3
    c.account_id = account_id
    c.name = "Hero"
    c.room_id = "zone:room"
    c.digi_balance = 10
    c.pvp_enabled = False
    c.reputation = 0
    c.stats = {}
    c.inventory = []
    return c


# ---- patch_account ----------------------------------------------------------


def test_patch_account_missing_returns_none():
    async def check():
        srv, _ = _server(_FakeSession(get_row=None))
        assert await player_accounts.patch_account(srv, 99, {"is_gm": True}) is None

    asyncio.run(check())


def test_patch_account_credit_add_clamps_at_zero_and_notifies_actor():
    async def check():
        acc = _account(credits=10)
        srv, calls = _server(_FakeSession(get_row=acc))
        out = await player_accounts.patch_account(
            srv, 7, {"echo_credits_add": -999}, actor={"username": "gm1", "role": "gm"}
        )
        assert out["echo_credits"] == 0  # clamped, never negative
        assert len(calls["audit"]) == 1
        assert calls["grant"] == []
        _, kw = calls["audit"][0]
        assert any("-10" in ln for ln in kw["summary_lines"])  # actual delta, not the raw -999

    asyncio.run(check())


def test_patch_account_grant_without_actor_uses_grant_notification():
    async def check():
        acc = _account(credits=10)
        srv, calls = _server(_FakeSession(get_row=acc))
        out = await player_accounts.patch_account(srv, 7, {"echo_credits_add": 25})
        assert out["echo_credits"] == 35
        assert calls["audit"] == []
        assert calls["grant"] == [(7, {"added": 25, "new_balance": 35})]

    asyncio.run(check())


def test_patch_account_gm_toggle_audited_only_on_change():
    async def check():
        acc = _account(is_gm=True)
        srv, calls = _server(_FakeSession(get_row=acc))
        # setting is_gm to its current value produces no audit lines → no notification
        await player_accounts.patch_account(srv, 7, {"is_gm": True}, actor={"username": "gm1"})
        assert calls["audit"] == []

    asyncio.run(check())


# ---- patch_character --------------------------------------------------------


def test_patch_character_rejects_wrong_account():
    async def check():
        char = _character(account_id=42)  # belongs to another account
        srv, _ = _server(_FakeSession(get_row=char))
        assert await player_accounts.patch_character(srv, 7, 3, {"digi_balance": 5}) is None

    asyncio.run(check())


def test_patch_character_clamps_balance_and_audits():
    async def check():
        char = _character()
        srv, calls = _server(_FakeSession(get_row=char))
        out = await player_accounts.patch_character(
            srv, 7, 3, {"digi_balance": -5, "pvp_enabled": True}, actor={"username": "gm1"}
        )
        assert out["digi_balance"] == 0
        assert out["pvp_enabled"] is True
        assert len(calls["audit"]) == 1
        _, kw = calls["audit"][0]
        assert kw["character_name"] == "Hero"

    asyncio.run(check())


def test_patch_character_blank_room_id_ignored():
    async def check():
        char = _character()
        srv, _ = _server(_FakeSession(get_row=char))
        out = await player_accounts.patch_character(srv, 7, 3, {"room_id": "   "})
        assert out["room_id"] == "zone:room"  # unchanged

    asyncio.run(check())


def test_patch_character_stats_migrated_and_proficiency_block_ensured():
    async def check():
        char = _character()
        srv, _ = _server(_FakeSession(get_row=char))
        out = await player_accounts.patch_character(srv, 7, 3, {"stats": {"hp": 12}})
        assert out["stats"]["hp"] == 12
        assert "conduit" in out["stats"] or any(
            k for k in out["stats"] if "proficien" in k or "conduit" in k
        )

    asyncio.run(check())
