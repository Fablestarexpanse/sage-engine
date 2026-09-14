"""AdminContext permission model and staff JWT round-trip."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from sage.admin.admin_security import (
    NAV_TOOL_IDS,
    AdminContext,
    decode_staff_token,
    issue_staff_token,
    jwt_secret_for_server,
)


def _ctx(role: str = "gm", permissions: dict | None = None) -> AdminContext:
    return AdminContext(
        staff_id=1,
        username="staff",
        display_name="Staff",
        role=role,
        permissions=permissions or {},
    )


class TestAdminContextTools(unittest.TestCase):
    def test_head_admin_gets_all_tools(self) -> None:
        ctx = _ctx(role="head_admin", permissions={"tools": ["forge"]})
        for tool in NAV_TOOL_IDS:
            self.assertTrue(ctx.may_use_tool(tool))
        self.assertEqual(ctx.allowed_tool_ids(), sorted(NAV_TOOL_IDS))

    def test_bypass_gets_all_tools(self) -> None:
        ctx = AdminContext.bypass()
        self.assertTrue(ctx.bypass_auth)
        for tool in NAV_TOOL_IDS:
            self.assertTrue(ctx.may_use_tool(tool))

    def test_gm_with_tool_list_gets_subset(self) -> None:
        ctx = _ctx(permissions={"tools": ["forge", "world"]})
        self.assertTrue(ctx.may_use_tool("forge"))
        self.assertTrue(ctx.may_use_tool("world"))
        self.assertFalse(ctx.may_use_tool("players"))
        self.assertEqual(ctx.allowed_tool_ids(), ["forge", "world"])

    def test_gm_with_empty_tool_list_gets_nothing(self) -> None:
        ctx = _ctx(permissions={"tools": []})
        self.assertFalse(ctx.may_use_tool("forge"))
        self.assertEqual(ctx.allowed_tool_ids(), [])

    def test_gm_without_tools_key_gets_all(self) -> None:
        ctx = _ctx(permissions={})
        self.assertTrue(ctx.may_use_tool("forge"))


class TestAdminContextZones(unittest.TestCase):
    def test_star_means_all_zones(self) -> None:
        ctx = _ctx(permissions={"zones": ["*"]})
        self.assertTrue(ctx.may_write_zone("anything"))

    def test_explicit_zone_list(self) -> None:
        ctx = _ctx(permissions={"zones": ["testzone"]})
        self.assertTrue(ctx.may_write_zone("testzone"))
        self.assertFalse(ctx.may_write_zone("other_zone"))

    def test_head_admin_writes_any_zone(self) -> None:
        ctx = _ctx(role="head_admin", permissions={"zones": ["testzone"]})
        self.assertTrue(ctx.may_write_zone("other_zone"))


def _server(secret: str | None, auth_required: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            server=SimpleNamespace(
                admin_jwt_secret=secret,
                admin_auth_required=auth_required,
            )
        )
    )


class TestStaffJwt(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure the env-var override does not leak into these tests
        import unittest.mock as mock

        patcher = mock.patch.dict(
            "os.environ", {"SAGE_ADMIN_JWT_SECRET": "", "FABLESTAR_ADMIN_JWT_SECRET": ""}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_round_trip(self) -> None:
        server = _server("unit-test-secret-0123456789abcdef0123456789abcdef")
        token = issue_staff_token(server, staff_id=42)
        self.assertEqual(decode_staff_token(server, token), 42)

    def test_garbage_token_rejected(self) -> None:
        server = _server("unit-test-secret-0123456789abcdef0123456789abcdef")
        with self.assertRaises(ValueError):
            decode_staff_token(server, "not-a-jwt")

    def test_wrong_secret_rejected(self) -> None:
        secret_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        secret_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        token = issue_staff_token(_server(secret_a), staff_id=1)
        with self.assertRaises(ValueError):
            decode_staff_token(_server(secret_b), token)

    def test_secret_required_when_auth_on(self) -> None:
        with self.assertRaises(RuntimeError):
            jwt_secret_for_server(_server(None, auth_required=True))

    def test_dev_fallback_when_auth_off(self) -> None:
        secret = jwt_secret_for_server(_server(None, auth_required=False))
        self.assertTrue(secret)


if __name__ == "__main__":
    unittest.main()
