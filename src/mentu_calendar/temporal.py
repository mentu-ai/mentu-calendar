"""Host-independent temporal core: instant <-> wall-clock, DST-policy aware.

Uses the pinned-bundle zones from :mod:`tz`. Wall <-> instant resolution follows PEP 495 folds:
an unambiguous time has equal fold-0/fold-1 offsets; a fall-back *overlap* has ``off0 > off1``; a
spring-forward *gap* has ``off0 < off1``. `now` is never read from the host.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from typing import Any

from .errors import CalendarError
from .tz import get_zone

_UTC = UTC
_EPOCH = datetime(1970, 1, 1, tzinfo=_UTC)
_POLICY_VALUES = frozenset({"earliest", "latest", "reject"})
_WALL_FIELDS = ("year", "month", "day", "hour", "minute", "second")


# ---- floating (zone-free) wall <-> epoch seconds -------------------------------------------------
def wall_to_epoch_sec(w: dict[str, int]) -> int:
    return _to_days(w["year"], w["month"], w["day"]) * 86400 + w["hour"] * 3600 + w["minute"] * 60 + w["second"]


def epoch_sec_to_wall(sec: int) -> dict[str, int]:
    days, rem = divmod(sec, 86400)
    y, mo, d = _from_days(days)
    return {"year": y, "month": mo, "day": d, "hour": rem // 3600, "minute": (rem % 3600) // 60, "second": rem % 60}


def _to_days(y: int, m: int, d: int) -> int:
    yy = y - (1 if m <= 2 else 0)
    era = (yy if yy >= 0 else yy - 399) // 400
    yoe = yy - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _from_days(z: int) -> tuple[int, int, int]:
    zz = z + 719468
    era = (zz if zz >= 0 else zz - 146096) // 146097
    doe = zz - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y + 1 if m <= 2 else y), m, d


# ---- validation ----------------------------------------------------------------------------------
def validate_wall(w: Any) -> dict[str, int]:
    if not isinstance(w, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "wall must be an object", {})
    out: dict[str, int] = {}
    for f in _WALL_FIELDS:
        v = w.get(f)
        if not isinstance(v, int) or isinstance(v, bool):
            raise CalendarError("SCHEMA_VALIDATION_ERROR", f"wall.{f} must be an integer", {})
        out[f] = v
    ok = (
        1 <= out["month"] <= 12
        and 1 <= out["day"] <= calendar.monthrange(out["year"], out["month"])[1]
        and 0 <= out["hour"] <= 23
        and 0 <= out["minute"] <= 59
        and 0 <= out["second"] <= 59
    )
    if not ok:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "Wall-clock fields are out of range", {"wall": out})
    return out


def validate_dst_policy(policy: Any) -> tuple[str, str]:
    if policy is None:
        raise CalendarError("MISSING_DST_POLICY", "An explicit dstPolicy is required", {})
    gap = policy.get("gap") if isinstance(policy, dict) else None
    overlap = policy.get("overlap") if isinstance(policy, dict) else None
    if gap not in _POLICY_VALUES or overlap not in _POLICY_VALUES:
        raise CalendarError(
            "SCHEMA_VALIDATION_ERROR",
            'dstPolicy.gap and dstPolicy.overlap must each be "earliest", "latest", or "reject"',
            {"dstPolicy": policy},
        )
    return gap, overlap


# ---- instant -> wall -----------------------------------------------------------------------------
def _offset_abbr(zone, t_sec: int) -> tuple[int, str, bool]:
    dt = (_EPOCH + timedelta(seconds=t_sec)).astimezone(zone)
    off = dt.utcoffset()
    assert off is not None  # an aware datetime always has a UTC offset
    return int(off.total_seconds()), dt.tzname() or "", bool(dt.dst())


def instant_to_wall(zone_id: str, epoch_ms: int) -> dict[str, Any]:
    zone = get_zone(zone_id)
    t_sec = epoch_ms // 1000  # floor to whole seconds
    off, abbr, isdst = _offset_abbr(zone, t_sec)
    return {"wall": epoch_sec_to_wall(t_sec + off), "offsetSeconds": off, "abbreviation": abbr, "isDst": isdst}


# ---- wall -> instant (DST-policy aware) ----------------------------------------------------------
def _finalize(zone, t_sec: int, resolution: str, fold: int) -> dict[str, Any]:
    off, abbr, _ = _offset_abbr(zone, t_sec)
    return {
        "instant": {"epochMs": t_sec * 1000},
        "offsetSeconds": off,
        "abbreviation": abbr,
        "fold": fold,
        "resolution": resolution,
    }


def wall_to_instant(zone_id: str, wall: dict[str, int], gap: str, overlap: str) -> dict[str, Any]:
    zone = get_zone(zone_id)
    naive = datetime(wall["year"], wall["month"], wall["day"], wall["hour"], wall["minute"], wall["second"])
    dt0 = naive.replace(tzinfo=zone, fold=0)
    dt1 = naive.replace(tzinfo=zone, fold=1)
    off0, off1 = dt0.utcoffset(), dt1.utcoffset()
    assert off0 is not None and off1 is not None  # aware datetimes always have offsets
    t0, t1 = int(dt0.timestamp()), int(dt1.timestamp())

    if off0 == off1:
        return _finalize(zone, t0, "exact", 0)
    if off0 > off1:  # fall-back overlap
        if overlap == "reject":
            raise CalendarError(
                "AMBIGUOUS_WALL_TIME", "Wall time is ambiguous (fall-back overlap)", {"zoneId": zone_id, "wall": wall}
            )
        return _finalize(zone, t0, "overlap", 0) if overlap == "earliest" else _finalize(zone, t1, "overlap", 1)
    # off0 < off1 -> spring-forward gap
    if gap == "reject":
        raise CalendarError(
            "NONEXISTENT_WALL_TIME", "Wall time does not exist (spring-forward gap)", {"zoneId": zone_id, "wall": wall}
        )
    return _finalize(zone, min(t0, t1), "gap", 0) if gap == "earliest" else _finalize(zone, max(t0, t1), "gap", 0)
