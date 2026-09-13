"""Play session tokens — round-trip, expiry, and strict separation from staff tokens."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from sage.admin.admin_security import decode_staff_token, issue_staff_token
from sage.services.play_tokens import decode_play_token, issue_play_token


def _server(secret: str = "unit-test-secret-0123456789abcdef0123456789abcdef") -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            server=SimpleNamespace(admin_jwt_secret=secret, admin_auth_required=True)
        )
    )


class TestPlayTokens(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict("os.environ", {"FABLESTAR_ADMIN_JWT_SECRET": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = _server()

    def test_round_trip(self) -> None:
        token = issue_play_token(self.server, account_id=7)
        self.assertEqual(decode_play_token(self.server, token), 7)

    def test_garbage_rejected(self) -> None:
        with self.assertRaises(ValueError):
            decode_play_token(self.server, "not-a-jwt")

    def test_expired_rejected(self) -> None:
        token = issue_play_token(self.server, account_id=7, ttl_seconds=-10)
        with self.assertRaises(ValueError):
            decode_play_token(self.server, token)

    def test_play_token_rejected_by_staff_decoder(self) -> None:
        """Account ids and staff ids overlap numerically — cross-use must fail."""
        play = issue_play_token(self.server, account_id=1)
        with self.assertRaises(ValueError):
            decode_staff_token(self.server, play)

    def test_staff_token_rejected_by_play_decoder(self) -> None:
        staff = issue_staff_token(self.server, staff_id=1)
        with self.assertRaises(ValueError):
            decode_play_token(self.server, staff)


if __name__ == "__main__":
    unittest.main()
