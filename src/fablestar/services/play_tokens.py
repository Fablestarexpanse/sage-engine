"""Play session tokens — JWT issued at /play/auth/login, accepted on later /play/* calls.

Tokens carry ``kind: "play"`` so they can never be used against admin routes
(``decode_staff_token`` rejects any token with a ``kind`` claim), and vice versa.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import jwt

from fablestar.admin.admin_security import jwt_secret_for_server

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

PLAY_TOKEN_TTL_SECONDS = 7 * 86400  # one week — players stay logged in across sessions


def issue_play_token(
    server: FablestarServer, account_id: int, ttl_seconds: int = PLAY_TOKEN_TTL_SECONDS
) -> str:
    secret = jwt_secret_for_server(server)
    now = int(time.time())
    payload = {"sub": str(account_id), "kind": "play", "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_play_token(server: FablestarServer, token: str) -> int:
    """Return the account_id for a valid play token; raise ValueError otherwise."""
    secret = jwt_secret_for_server(server)
    try:
        data = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise ValueError("invalid_token") from e
    if data.get("kind") != "play":
        raise ValueError("invalid_token")
    sub = data.get("sub")
    if sub is None:
        raise ValueError("invalid_token")
    return int(sub)
