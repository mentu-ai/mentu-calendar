"""Determinism, offline, and canonical-serialization guarantees."""

from __future__ import annotations

import socket

from mentu_calendar import OPERATIONS, dispatch
from mentu_calendar.canonical import canonical_json, sha256_canonical

DP = {"gap": "earliest", "overlap": "earliest"}
_MASTER = {
    "id": "m",
    "calendarId": "c",
    "start": {"year": 2025, "month": 1, "day": 1, "hour": 9, "minute": 0, "second": 0},
    "end": {"year": 2025, "month": 1, "day": 1, "hour": 9, "minute": 30, "second": 0},
    "timeZone": "America/New_York",
    "recurrenceRule": {"frequency": "DAILY", "count": 5},
}
_SAMPLES = [
    ("resolve_timezone", {"zoneId": "Asia/Tokyo", "instant": {"epochMs": 1736942400000}}),
    (
        "resolve_timezone",
        {
            "zoneId": "America/New_York",
            "wall": {"year": 2025, "month": 11, "day": 2, "hour": 1, "minute": 30, "second": 0},
            "dstPolicy": {"gap": "reject", "overlap": "latest"},
        },
    ),
    ("expand_recurrence", {"master": _MASTER, "dstPolicy": DP}),
    (
        "find_slots",
        {
            "timeZone": "Europe/Paris",
            "candidateWindows": [{"start": {"epochMs": 1735808400000}, "end": {"epochMs": 1735837200000}}],
            "durationMinutes": 60,
        },
    ),
]


def test_byte_identical_repeat() -> None:
    for op, inp in _SAMPLES:
        first = canonical_json(dispatch(op, inp))
        assert first and canonical_json(dispatch(op, inp)) == first


def test_no_network(monkeypatch) -> None:
    def _blocked(*_a, **_k):
        raise AssertionError("engine attempted network access")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    for op, inp in _SAMPLES:
        assert dispatch(op, inp)["ok"] is True


def test_every_operation_dispatches() -> None:
    for op in OPERATIONS:
        assert "ok" in dispatch(op, {})


def test_canonical_rules() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert canonical_json({"z": {"b": 1, "a": 2}, "a": [3, 1]}) == '{"a":[3,1],"z":{"a":2,"b":1}}'
    assert canonical_json({"x": -0.0}) == '{"x":0}'
    assert sha256_canonical({"a": 1, "b": 2}) == sha256_canonical({"b": 2, "a": 1})
