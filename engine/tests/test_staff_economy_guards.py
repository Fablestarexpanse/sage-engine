"""Direct service tests: staff-lockout guards and the echo-credit debit/refund path.

Both services talk to Postgres through server.db.session_factory; here that is a
fake async session scripted per test — enough to exercise the guard branches and
money math the HTTP-layer tests monkeypatch away.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from sage.admin import staff_service
from sage.services.economy import EconomyService
from sage.state.models import Account, AdminStaff
from tests.fakes import fake_wallet


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value


class _FakeSession:
    """Scripted async session: .get() row, then execute() results in order."""

    def __init__(self, get_row=None, execute_results=()):
        self._get_row = get_row
        self._execute_results = list(execute_results)
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return self._get_row

    async def execute(self, stmt):
        return _Result(self._execute_results.pop(0))

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def refresh(self, row):
        pass


def _server_with(session):
    return SimpleNamespace(
        db=SimpleNamespace(session_factory=lambda: session),
        config=SimpleNamespace(
            comfyui=SimpleNamespace(
                economy_enabled=True,
                currency_display_name="credits",
                credits_per_usd=100,
            ),
        ),
        wallet=fake_wallet(),
    )


def _head_admin(staff_id=1, active=True):
    row = AdminStaff()
    row.id = staff_id
    row.username = f"staff{staff_id}"
    row.display_name = "Head"
    row.role = "head_admin"
    row.permissions = {}
    row.is_active = active
    return row


# ---- staff lockout guards ---------------------------------------------------


def test_cannot_demote_last_head_admin():
    async def check():
        # head_admin count query returns 1 → demotion refused
        session = _FakeSession(get_row=_head_admin(), execute_results=[1])
        with pytest.raises(HTTPException) as ei:
            await staff_service.apply_staff_patch(_server_with(session), 1, {"role": "gm"})
        assert ei.value.detail == "cannot_remove_last_head_admin"
        assert not session.committed

    asyncio.run(check())


def test_cannot_deactivate_last_head_admin():
    async def check():
        session = _FakeSession(get_row=_head_admin(), execute_results=[1])
        with pytest.raises(HTTPException) as ei:
            await staff_service.apply_staff_patch(_server_with(session), 1, {"is_active": False})
        assert ei.value.detail == "cannot_deactivate_last_head_admin"
        assert not session.committed

    asyncio.run(check())


def test_demote_allowed_when_another_head_admin_exists():
    async def check():
        session = _FakeSession(get_row=_head_admin(), execute_results=[2])
        row = await staff_service.apply_staff_patch(_server_with(session), 1, {"role": "gm"})
        assert row.role == "gm"
        assert session.committed

    asyncio.run(check())


def test_create_staff_rejects_taken_username():
    async def check():
        session = _FakeSession(execute_results=[_head_admin(7)])
        with pytest.raises(HTTPException) as ei:
            await staff_service.create_staff(
                _server_with(session),
                username="staff7",
                password="longenough1",
                display_name="",
                role="gm",
                permissions={},
            )
        assert ei.value.detail == "username_taken"

    asyncio.run(check())


# ---- economy debit / refund -------------------------------------------------


def _account(credits=100):
    acc = Account()
    acc.id = 5
    acc.ai_credits = credits
    return acc


def test_debit_success_deducts_and_commits():
    async def check():
        acc = _account(100)
        session = _FakeSession(execute_results=[acc])
        ok, err, balance_after, charged = await EconomyService(
            _server_with(session)
        ).debit_for_generation(5, 30)
        assert ok and err == {}
        assert balance_after == 70 and charged == 30
        assert acc.ai_credits == 70
        assert session.committed

    asyncio.run(check())


def test_debit_insufficient_rolls_back():
    async def check():
        acc = _account(10)
        session = _FakeSession(execute_results=[acc])
        ok, err, balance_after, charged = await EconomyService(
            _server_with(session)
        ).debit_for_generation(5, 30)
        assert not ok
        assert err["error"] == "insufficient_credits"
        assert err["balance"] == 10 and err["required"] == 30
        assert charged == 0
        assert acc.ai_credits == 10
        assert session.rolled_back and not session.committed

    asyncio.run(check())


def test_debit_disabled_economy_charges_nothing():
    async def check():
        session = _FakeSession(execute_results=[42])  # read_balance scalar
        server = _server_with(session)
        server.config.comfyui.economy_enabled = False
        ok, err, balance_after, charged = await EconomyService(server).debit_for_generation(5, 30)
        assert ok and charged == 0 and balance_after == 42

    asyncio.run(check())


def test_refund_restores_credits():
    async def check():
        acc = _account(70)
        session = _FakeSession(execute_results=[acc])
        await EconomyService(_server_with(session)).refund(5, 30)
        assert acc.ai_credits == 100
        assert session.committed

    asyncio.run(check())
