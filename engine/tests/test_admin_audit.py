"""The admin audit middleware records staff writes, not reads, logins or generation, and hides secrets."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from sage.admin import audit
from sage.admin.audit import AdminAuditMiddleware, should_record


@pytest.mark.parametrize(
    "method, path, recorded",
    [
        ("PATCH", "/admin/staff/3", True),
        ("PUT", "/admin/lexicon/login.motd", True),
        ("DELETE", "/world/entities/rat_1", True),
        ("POST", "/plugins/agents/admin/agents/sela/pause", True),
        ("GET", "/admin/staff", False),
        ("POST", "/admin/auth/login", False),
        ("POST", "/forge/generate", False),
        ("POST", "/llm/test-completion", False),
        ("POST", "/play/auth/register", False),
        ("POST", "/admin/characters/4/move", False),  # records its own, richer row
        ("POST", "/admin/player-accounts/2/suspend", False),
    ],
)
def test_what_is_recorded(method, path, recorded):
    assert should_record(method, path) is recorded


def test_middleware_records_a_successful_write_with_the_route_and_scrubbed_body(monkeypatch):
    rows = []

    async def fake_record(server, ctx, action, target, **detail):
        rows.append((getattr(ctx, "username", None), action, target, detail))

    monkeypatch.setattr(audit, "record", fake_record)
    app = FastAPI()

    @app.middleware("http")
    async def pretend_auth(request: Request, call_next):
        class Ctx:
            username = "head"

        request.state.admin_ctx = Ctx()
        return await call_next(request)

    @app.patch("/admin/staff/{staff_id}")
    async def patch_staff(staff_id: int, request: Request):
        await request.json()
        return {"ok": True}

    @app.patch("/admin/broken")
    async def broken():
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="nope")

    app.add_middleware(AdminAuditMiddleware, server=object())
    # The audit row is written after the response, so the staff member set by auth is there either way.
    client = TestClient(app)
    assert (
        client.patch("/admin/staff/3", json={"role": "gm", "password": "secret-pass"}).status_code
        == 200
    )
    assert client.patch("/admin/broken", json={}).status_code == 400
    assert rows == [
        (
            "head",
            "PATCH /admin/staff/{staff_id}",
            "/admin/staff/3",
            {"path_params": {"staff_id": "3"}, "body": {"role": "gm", "password": "(changed)"}},
        )
    ]


def test_record_never_raises_when_the_database_fails():
    class Broken:
        def session_factory(self):
            raise RuntimeError("database down")

    server = type("S", (), {"db": Broken()})()
    asyncio.run(audit.record(server, None, "x", "y"))
