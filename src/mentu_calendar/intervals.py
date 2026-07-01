"""Half-open ``[start, end)`` interval algebra over epoch-millisecond integers.

Touching intervals do not overlap; back-to-back events do not conflict.
"""

from __future__ import annotations

from typing import Any

from .errors import CalendarError

Ms = tuple[int, int]
DEFAULT_BUSY = frozenset({"busy", "unavailable"})


def as_ms(interval: Any) -> Ms:
    s = interval["start"]["epochMs"]
    e = interval["end"]["epochMs"]
    if not isinstance(s, int) or not isinstance(e, int) or isinstance(s, bool) or isinstance(e, bool):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "interval bounds must be integer epochMs", {})
    if e < s:
        raise CalendarError(
            "INVALID_INTERVAL",
            "Interval end must not precede its start",
            {"interval": {"start": {"epochMs": s}, "end": {"epochMs": e}}},
        )
    return (s, e)


def to_interval(s: int, e: int) -> dict[str, Any]:
    return {"start": {"epochMs": s}, "end": {"epochMs": e}}


def coalesce(intervals: list[Ms], merge_touch: bool = True) -> list[Ms]:
    """Sort, drop zero-length, and merge overlapping (and touching when ``merge_touch``) intervals."""
    out: list[Ms] = []
    for s, e in sorted(iv for iv in intervals if iv[0] < iv[1]):
        if out and (s < out[-1][1] or (merge_touch and s == out[-1][1])):
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract(window: Ms, busy: list[Ms]) -> list[Ms]:
    """``window`` minus a (coalesced) busy list, clipped to the window."""
    ws, we = window
    free: list[Ms] = []
    cur = ws
    for bs, be in busy:
        if be <= ws or bs >= we:
            continue
        lo, hi = max(bs, ws), min(be, we)
        if cur < lo:
            free.append((cur, lo))
        cur = max(cur, hi)
    if cur < we:
        free.append((cur, we))
    return free


def strict_overlap(a: Ms, b: Ms) -> Ms | None:
    s, e = max(a[0], b[0]), min(a[1], b[1])
    return (s, e) if s < e else None


def clip(iv: Ms, window: Ms) -> Ms | None:
    s, e = max(iv[0], window[0]), min(iv[1], window[1])
    return (s, e) if s < e else None


def occupies(event: dict[str, Any], treat_tentative_as_busy: bool, busy_availabilities: frozenset[str]) -> bool:
    if event.get("status", "confirmed") == "cancelled":
        return False
    avail = event.get("availability", "busy")
    if avail == "tentative":
        return treat_tentative_as_busy
    return avail in busy_availabilities


def conflict_occupies(event: dict[str, Any]) -> bool:
    """Occupation for conflict detection: only cancelled / free / not_supported are excluded."""
    if event.get("status", "confirmed") == "cancelled":
        return False
    return event.get("availability", "busy") not in ("free", "not_supported")
