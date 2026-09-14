"""Lease availability, legacy rental parsing, and telemetry call safety."""

import asyncio
import json

from fablestar import telemetry
from fablestar.commands.rent import free_rooms, read_rentals
from fablestar.world.models import LodgingModel

LODGING = LodgingModel(rooms=["z:a", "z:b"], price=8, lease_minutes=60)


class _FakeClient:
    def __init__(self, data):
        self.data = data

    async def hgetall(self, key):
        return self.data


class _FakeRedis:
    def __init__(self, data):
        self.client = _FakeClient(data)


def test_free_rooms_counts_lapsed_leases_as_free():
    rentals = {"z:a": {"tenant": "x", "until": 50.0}, "z:b": {"tenant": "y", "until": 500.0}}
    assert free_rooms(LODGING, rentals, now=100.0) == ["z:a"]


def test_free_rooms_all_free_when_unrented():
    assert free_rooms(LODGING, {}, now=100.0) == ["z:a", "z:b"]


def test_legacy_plain_rental_values_read_as_expired():
    redis = _FakeRedis({b"z:a": b"Aldo Vex", b"z:b": json.dumps({"tenant": "Meri", "until": 9e9})})
    rentals = asyncio.run(read_rentals(redis))
    assert rentals["z:a"] == {"tenant": "Aldo Vex", "until": 0}
    assert free_rooms(LODGING, rentals, now=100.0) == ["z:a"]


def test_log_event_accepts_a_field_named_kind(tmp_path, monkeypatch):
    # The overnight buy/sell crash: a 'kind' field collided with the event
    # type argument. It must never raise, even with telemetry enabled.
    monkeypatch.setattr(telemetry, "_disabled", False)
    monkeypatch.setattr(telemetry, "LOG_DIR", tmp_path)
    monkeypatch.setattr(telemetry, "_handles", {})
    telemetry.log_event("trade", kind="buy", price=4)
    for fh in telemetry._handles.values():
        fh.close()
    line = json.loads(next(tmp_path.glob("events-*.jsonl")).read_text(encoding="utf-8"))
    assert line["kind"] == "trade"
    assert line["price"] == 4
