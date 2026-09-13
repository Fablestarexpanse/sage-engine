"""The `lodging:` block and lease bookkeeping over the `rentals` hash (room_id -> lease JSON)."""

import json
from typing import Any

from pydantic import BaseModel, Field

RENTALS_KEY = "rentals"
RENEW_WINDOW_S = 15 * 60  # renewing is allowed once a lease has < 15 min left


class LodgingModel(BaseModel):
    """A rent desk: this room lets the listed rooms on timed leases."""

    name: str = "the lodging"
    rooms: list[str] = Field(min_length=1)  # full room ids
    price: int = Field(default=15, gt=0)
    lease_minutes: int = Field(default=80, gt=0)


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else value


def parse_rentals(raw: dict[Any, Any] | None) -> dict[str, dict]:
    """room_id -> {"tenant": str, "until": float}. Legacy plain values read as expired."""
    out = {}
    for k, v in (raw or {}).items():
        v = _text(v)
        try:
            lease = json.loads(v)
            if not isinstance(lease, dict):
                raise ValueError
        except ValueError:
            lease = {"tenant": v, "until": 0}
        out[_text(k)] = lease
    return out


def free_rooms(lodging: LodgingModel, rentals: dict[str, dict], now: float) -> list[str]:
    """Rooms in this lodging with no lease or a lapsed one."""
    return [r for r in lodging.rooms if float(rentals.get(r, {}).get("until", 0)) <= now]
