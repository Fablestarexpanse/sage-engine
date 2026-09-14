"""Telemetry call safety."""

import json

from sage import telemetry


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
