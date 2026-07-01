"""check_availability, detect_conflicts, find_slots — half-open interval scheduling."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..errors import CalendarError
from ..intervals import (
    DEFAULT_BUSY,
    as_ms,
    clip,
    coalesce,
    conflict_occupies,
    occupies,
    strict_overlap,
    subtract,
    to_interval,
)
from ..temporal import instant_to_wall, validate_dst_policy, wall_to_instant

MAX_SLOTS = 10000
DEFAULT_PROFILE = "default"
DEFAULT_POLICY_VERSION = "2026.1"


def check_availability(inp: Any) -> tuple[dict[str, Any], str | None]:
    if "window" not in inp:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "window is required", {})
    window = as_ms(inp["window"])
    treat = bool(inp.get("treatTentativeAsBusy", False))
    busy_avails = frozenset(inp.get("busyAvailabilities", DEFAULT_BUSY))
    occ = [as_ms(e) for e in inp.get("events", []) if occupies(e, treat, busy_avails)]
    # Coalesce the full busy set (merge touching), then clip each block to the window: the reported
    # busy[] and free[] both live inside [window.start, window.end).
    busy = [c for b in coalesce(occ, merge_touch=True) if (c := clip(b, window)) is not None]
    free = subtract(window, busy)
    return {"busy": [to_interval(*b) for b in busy], "free": [to_interval(*f) for f in free]}, None


def detect_conflicts(inp: Any) -> tuple[dict[str, Any], str | None]:
    window = as_ms(inp["window"]) if "window" in inp else None
    items: list[tuple[str, tuple[int, int]]] = []
    for e in inp.get("events", []):
        if not conflict_occupies(e):
            continue
        iv = as_ms(e)
        if window is not None:
            c = clip(iv, window)
            if c is None:
                continue
            iv = c
        items.append((e["id"], iv))
    conflicts: list[dict[str, Any]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            ida, iva = items[i]
            idb, ivb = items[j]
            ov = strict_overlap(iva, ivb)
            if ov is not None:
                a, b = (ida, idb) if ida <= idb else (idb, ida)
                conflicts.append({"a": a, "b": b, "overlap": to_interval(*ov)})
    conflicts.sort(key=lambda c: (c["a"], c["b"], c["overlap"]["start"]["epochMs"], c["overlap"]["end"]["epochMs"]))
    return {"conflicts": conflicts}, None


def _business_hour_intervals(
    tz: str, ws: int, we: int, business_hours: list, gap: str, overlap: str
) -> list[tuple[int, int]]:
    start_wall = instant_to_wall(tz, ws)["wall"]
    end_wall = instant_to_wall(tz, we)["wall"]
    d = date(start_wall["year"], start_wall["month"], start_wall["day"])
    dend = date(end_wall["year"], end_wall["month"], end_wall["day"])
    by_wd: dict[int, list[tuple[str, str]]] = {}
    for e in business_hours:
        by_wd.setdefault(e["weekday"], []).append((e["start"], e["end"]))
    out: list[tuple[int, int]] = []
    while d <= dend:
        for shm, ehm in by_wd.get(d.isoweekday(), []):
            sh, sm = (int(x) for x in shm.split(":"))
            eh, em = (int(x) for x in ehm.split(":"))
            base = {"year": d.year, "month": d.month, "day": d.day, "second": 0}
            si = wall_to_instant(tz, {**base, "hour": sh, "minute": sm}, gap, overlap)["instant"]["epochMs"]
            ei = wall_to_instant(tz, {**base, "hour": eh, "minute": em}, gap, overlap)["instant"]["epochMs"]
            if ei > si:
                out.append((si, ei))
        d += timedelta(days=1)
    return coalesce(out)


def find_slots(inp: Any) -> tuple[dict[str, Any], str | None]:
    tz = inp.get("timeZone")
    if not tz:
        raise CalendarError("MISSING_TIME_ZONE", "timeZone is required", {})
    if not isinstance(tz, str):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "timeZone must be a string", {})
    duration = inp.get("durationMinutes")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "durationMinutes must be a positive integer", {})
    if "candidateWindows" not in inp or not inp["candidateWindows"]:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "candidateWindows is required and non-empty", {})

    cons = inp.get("constraints") or {}
    buf_before = int(cons.get("bufferBeforeMinutes", 0))
    buf_after = int(cons.get("bufferAfterMinutes", 0))
    min_notice = int(cons.get("minNoticeMinutes", 0))
    treat = bool(cons.get("treatTentativeAsBusy", False))
    busy_avails = frozenset(cons.get("busyAvailabilities", DEFAULT_BUSY))
    gran = int(cons.get("granularityMinutes", duration))
    business_hours = cons.get("businessHours")
    ranking = (inp.get("ranking") or {}).get("strategy", "earliest")
    profile = inp.get("policyProfile") or DEFAULT_PROFILE
    max_slots = min(int(inp.get("maxSlots", MAX_SLOTS)), MAX_SLOTS)

    dur_ms, gran_ms = duration * 60000, gran * 60000
    windows = coalesce([as_ms(w) for w in inp["candidateWindows"]])

    occ: list[tuple[int, int]] = []
    for e in inp.get("events", []):
        if occupies(e, treat, busy_avails):
            s, en = as_ms(e)
            occ.append((s - buf_after * 60000, en + buf_before * 60000))
    busy = coalesce(occ)

    free: list[tuple[int, int]] = []
    for w in windows:
        free.extend(subtract(w, busy))

    if business_hours:
        if inp.get("dstPolicy") is None:
            raise CalendarError(
                "MISSING_DST_POLICY",
                "dstPolicy is required when businessHours are given (wall-clock resolution)",
                {},
            )
        gap, overlap = validate_dst_policy(inp.get("dstPolicy"))
        ws, we = min(w[0] for w in windows), max(w[1] for w in windows)
        bh = _business_hour_intervals(tz, ws, we, business_hours, gap, overlap)
        free = sorted(ov for f in free for b in bh if (ov := strict_overlap(f, b)) is not None)

    floor: int | None = None
    if min_notice > 0:
        now = inp.get("now")
        if not isinstance(now, dict) or not isinstance(now.get("epochMs"), int):
            raise CalendarError("SCHEMA_VALIDATION_ERROR", "now (Instant) is required when minNoticeMinutes > 0", {})
        floor = now["epochMs"] + min_notice * 60000

    slots: list[tuple[int, int]] = []
    for fs, fe in free:
        # Slots step by the granularity from the region start, or from the min-notice floor when it
        # falls inside the region — the floor itself is a valid start, not re-aligned to a grid.
        s = fs if floor is None else max(fs, floor)
        while s + dur_ms <= fe:
            slots.append((s, s + dur_ms))
            if len(slots) >= max_slots:
                break
            s += gran_ms
        if len(slots) >= max_slots:
            break
    slots.sort()
    result = {
        "slots": [to_interval(*sl) for sl in slots[:max_slots]],
        "ranking": ranking,
        "policyProfile": profile,
        "policyVersion": DEFAULT_POLICY_VERSION,
    }
    return result, DEFAULT_POLICY_VERSION
