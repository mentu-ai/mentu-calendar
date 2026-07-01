"""expand_recurrence, next_occurrence — RFC 5545 series materialization."""

from __future__ import annotations

from typing import Any

from ..errors import CalendarError
from ..recurrence import expand, next_after
from ..temporal import validate_dst_policy


def _master(inp: Any) -> dict[str, Any]:
    m = inp.get("master") if isinstance(inp, dict) else None
    if not isinstance(m, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "master is required", {})
    return m


def expand_recurrence(inp: Any) -> tuple[dict[str, Any], str | None]:
    gap, overlap = validate_dst_policy(inp.get("dstPolicy"))
    master = _master(inp)
    window = None
    if "window" in inp:
        w = inp["window"]
        ws, we = w["start"]["epochMs"], w["end"]["epochMs"]
        if we < ws:
            raise CalendarError(
                "INVALID_INTERVAL",
                "Interval end must not precede its start",
                {"interval": {"start": {"epochMs": ws}, "end": {"epochMs": we}}},
            )
        window = (ws, we)
    overrides = inp.get("overrides", [])
    for i, ov in enumerate(overrides):
        if ov["end"]["epochMs"] < ov["start"]["epochMs"]:
            raise CalendarError("INVALID_INTERVAL", f"overrides[{i}] end precedes start", {})
    occ = expand(master, gap, overlap, inp.get("exDates", []), overrides, window, inp.get("limit"))
    return {"occurrences": occ}, None


def next_occurrence(inp: Any) -> tuple[dict[str, Any], str | None]:
    gap, overlap = validate_dst_policy(inp.get("dstPolicy"))
    master = _master(inp)
    after = inp.get("after")
    if (
        not isinstance(after, dict)
        or not isinstance(after.get("epochMs"), int)
        or isinstance(after.get("epochMs"), bool)
    ):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "after (Instant) is required", {})
    occ = next_after(master, gap, overlap, inp.get("exDates", []), after["epochMs"])
    return {"occurrence": occ}, None
