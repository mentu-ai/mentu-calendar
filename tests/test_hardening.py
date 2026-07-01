"""Hardening + regression tests for behaviors found via differential fuzzing.

These lock determinism guarantees and resource bounds that are engine-specific (not tied to the
conformance vectors): host-state independence, recurrence caps, and clean errors on unsupported rules.
"""

from __future__ import annotations

import calendar
import time

from mentu_calendar import dispatch
from mentu_calendar.canonical import canonical_json

DP = {"gap": "earliest", "overlap": "earliest"}


def _master(rule, tz="UTC", start=None, end=None):
    s = start or {"year": 2025, "month": 1, "day": 1, "hour": 9, "minute": 0, "second": 0}
    e = end or {"year": 2025, "month": 1, "day": 1, "hour": 10, "minute": 0, "second": 0}
    return {"id": "m", "calendarId": "c", "start": s, "end": e, "timeZone": tz, "recurrenceRule": rule}


def test_wkst_independent_of_host_firstweekday() -> None:
    """WEEKLY;INTERVAL>1 expansion must not depend on the mutable global calendar.firstweekday()."""
    inp = {
        "master": _master(
            {
                "frequency": "WEEKLY",
                "interval": 2,
                "count": 8,
                "byDay": [{"weekday": 1}, {"weekday": 3}, {"weekday": 5}, {"weekday": 7}],
            }
        ),
        "dstPolicy": DP,
    }
    outs = set()
    original = calendar.firstweekday()
    try:
        for fw in (calendar.MONDAY, calendar.SUNDAY, calendar.SATURDAY, calendar.THURSDAY):
            calendar.setfirstweekday(fw)
            outs.add(canonical_json(dispatch("expand_recurrence", inp)))
    finally:
        calendar.setfirstweekday(original)
    assert len(outs) == 1


def test_recurrence_occurrence_cap_is_bounded() -> None:
    out = dispatch("expand_recurrence", {"master": _master({"frequency": "DAILY", "count": 100000}), "dstPolicy": DP})
    assert out["ok"] is False and out["error"]["code"] == "RECURRENCE_LIMIT_EXCEEDED"


def test_impossible_constraint_returns_empty_and_is_bounded() -> None:
    start = time.perf_counter()
    out = dispatch(
        "expand_recurrence",
        {"master": _master({"frequency": "MONTHLY", "byMonth": [2], "byMonthDay": [31], "count": 5}), "dstPolicy": DP},
    )
    assert time.perf_counter() - start < 5.0  # never scans to dateutil's year-9999 ceiling
    assert out["ok"] is True and out["result"]["occurrences"] == []


def test_unsupported_rule_is_a_clean_structured_error() -> None:
    out = dispatch(
        "expand_recurrence",
        {
            "dstPolicy": DP,
            "master": _master(
                {"frequency": "HOURLY", "interval": 4, "byMonthDay": [31, 15], "byHour": [18], "count": 5}
            ),
        },
    )
    # a clean code + message, never dateutil's internal "byxxx generates an empty set" string
    assert out["ok"] is False and out["error"]["code"] == "SCHEMA_VALIDATION_ERROR"
    assert "byxxx" not in out["error"]["message"]


def test_unbounded_recurrence_rejected() -> None:
    out = dispatch("expand_recurrence", {"master": _master({"frequency": "DAILY"}), "dstPolicy": DP})
    assert out["ok"] is False and out["error"]["code"] == "UNBOUNDED_RECURRENCE"


def test_count_counts_resolved_not_nominal_across_dst_gap() -> None:
    """A DST-gap occurrence skipped under reject must not consume COUNT (series still yields COUNT)."""
    out = dispatch(
        "expand_recurrence",
        {
            "dstPolicy": {"gap": "reject", "overlap": "reject"},
            "master": _master(
                {"frequency": "HOURLY", "interval": 2, "byMonthDay": [1, 30], "count": 15},
                tz="Europe/Dublin",
                start={"year": 2025, "month": 2, "day": 2, "hour": 1, "minute": 30, "second": 0},
                end={"year": 2025, "month": 2, "day": 2, "hour": 2, "minute": 30, "second": 0},
            ),
        },
    )
    assert out["ok"] is True and len(out["result"]["occurrences"]) == 15


def test_occurrence_kept_when_only_its_end_wall_is_ambiguous() -> None:
    """An occurrence whose END wall lands in a DST overlap under reject is still emitted (start is exact)."""
    out = dispatch(
        "expand_recurrence",
        {
            "dstPolicy": {"gap": "latest", "overlap": "reject"},
            "master": _master(
                {"frequency": "HOURLY", "byMonth": [6, 11], "count": 8},
                tz="America/Los_Angeles",
                start={"year": 2026, "month": 10, "day": 1, "hour": 9, "minute": 0, "second": 0},
                end={"year": 2026, "month": 10, "day": 1, "hour": 10, "minute": 0, "second": 0},
            ),
        },
    )
    starts = [o["startInstant"]["epochMs"] for o in out["result"]["occurrences"]]
    assert 1793516400000 in starts  # 2026-11-01 00:00 PDT, whose end wall 01:00 is ambiguous


def test_availability_busy_clipped_to_window() -> None:
    out = dispatch(
        "check_availability",
        {
            "window": {"start": {"epochMs": 1000}, "end": {"epochMs": 2000}},
            "events": [
                {"id": "a", "start": {"epochMs": 1500}, "end": {"epochMs": 2500}},
                {"id": "b", "start": {"epochMs": 500}, "end": {"epochMs": 800}},
            ],
        },
    )
    assert out["result"]["busy"] == [{"start": {"epochMs": 1500}, "end": {"epochMs": 2000}}]
