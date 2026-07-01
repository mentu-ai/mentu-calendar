#!/usr/bin/env python3
"""Regenerate the conformance fixtures by capturing an engine's canonical output.

Each vector is {op, input, expected}, where `expected` is the engine's full response
envelope. The engine is invoked as a CLI via the MENTU_CAL_ORACLE env var (a command
prefix), defaulting to the installed `mentu-calendar` console script — e.g.
`<prefix> call <op>`. Vectors are behavioral (input -> output) and are the binding
contract: any implementation must reproduce them. Regenerate only deliberately (e.g. on
a tzdata bump or when adding cases); the committed fixtures are the source of truth.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
VEC = ROOT / "conformance" / "vectors"

ORACLE = os.environ.get("MENTU_CAL_ORACLE", "mentu-calendar")
ORACLE_ARGV = shlex.split(ORACLE)


def run(op: str, payload: dict) -> dict:
    p = subprocess.run(ORACLE_ARGV + ["call", op], input=json.dumps(payload), capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"_unparsed": p.stdout, "_stderr": p.stderr, "_code": p.returncode}


def ems(y, mo, d, h=0, mi=0, s=0, tz="UTC") -> int:
    return int(datetime(y, mo, d, h, mi, s, tzinfo=ZoneInfo(tz)).timestamp() * 1000)


def inst(y, mo, d, h=0, mi=0, s=0, tz="UTC") -> dict:
    return {"epochMs": ems(y, mo, d, h, mi, s, tz)}


def wall(y, mo, d, h=0, mi=0, s=0) -> dict:
    return {"year": y, "month": mo, "day": d, "hour": h, "minute": mi, "second": s}


def iv(a: dict, b: dict) -> dict:
    return {"start": a, "end": b}


DP = {"gap": "earliest", "overlap": "earliest"}
cases: list[tuple[str, str, dict]] = []


def add(op, label, payload):
    cases.append((op, label, payload))


# ---- resolve_timezone: instant -> wall/offset across many zones + eras ----
ZONES = [
    "UTC",
    "America/New_York",
    "America/Los_Angeles",
    "America/Chicago",
    "America/Denver",
    "America/Sao_Paulo",
    "America/Mexico_City",
    "America/Argentina/Buenos_Aires",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Moscow",
    "Europe/Istanbul",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Kolkata",
    "Asia/Dubai",
    "Asia/Singapore",
    "Asia/Hong_Kong",
    "Asia/Kathmandu",
    "Asia/Tehran",
    "Australia/Sydney",
    "Australia/Perth",
    "Pacific/Auckland",
    "Pacific/Honolulu",
    "Pacific/Chatham",
    "Pacific/Kiritimati",
    "Africa/Cairo",
    "Africa/Johannesburg",
]
for z in ZONES:
    add("resolve_timezone", f"inst_winter_{z.replace('/', '_')}", {"zoneId": z, "instant": inst(2025, 1, 15, 12)})
    add("resolve_timezone", f"inst_summer_{z.replace('/', '_')}", {"zoneId": z, "instant": inst(2025, 7, 15, 12)})
# historical (pre-rule-change eras)
for z in ["America/New_York", "Europe/London", "America/Sao_Paulo", "Europe/Istanbul", "Asia/Shanghai"]:
    add("resolve_timezone", f"inst_1990_{z.replace('/', '_')}", {"zoneId": z, "instant": inst(1990, 7, 15, 12)})
    add("resolve_timezone", f"inst_2005_{z.replace('/', '_')}", {"zoneId": z, "instant": inst(2005, 3, 20, 12)})
# far-future (footer-expanded)
add("resolve_timezone", "inst_2050_ny", {"zoneId": "America/New_York", "instant": inst(2050, 7, 15, 12)})
add("resolve_timezone", "inst_2090_berlin", {"zoneId": "Europe/Berlin", "instant": inst(2090, 1, 15, 12)})
# wall -> instant: exact
add("resolve_timezone", "wall_exact_ny", {"zoneId": "America/New_York", "wall": wall(2025, 6, 1, 9), "dstPolicy": DP})
# fall-back overlap earliest/latest/reject
for pol in ["earliest", "latest", "reject"]:
    add(
        "resolve_timezone",
        f"wall_overlap_ny_{pol}",
        {
            "zoneId": "America/New_York",
            "wall": wall(2025, 11, 2, 1, 30),
            "dstPolicy": {"gap": "reject", "overlap": pol},
        },
    )
# spring-forward gap earliest/latest/reject
for pol in ["earliest", "latest", "reject"]:
    add(
        "resolve_timezone",
        f"wall_gap_ny_{pol}",
        {
            "zoneId": "America/New_York",
            "wall": wall(2025, 3, 9, 2, 30),
            "dstPolicy": {"gap": pol, "overlap": "earliest"},
        },
    )
# errors
add("resolve_timezone", "err_missing_tz", {"zoneId": ""})
add("resolve_timezone", "err_invalid_tz", {"zoneId": "Nowhere/Nope", "instant": inst(2025, 1, 1)})
add(
    "resolve_timezone",
    "err_both_wall_instant",
    {"zoneId": "UTC", "wall": wall(2025, 1, 1), "instant": inst(2025, 1, 1), "dstPolicy": DP},
)
add("resolve_timezone", "err_neither", {"zoneId": "UTC"})
add("resolve_timezone", "err_bad_epochms", {"zoneId": "UTC", "instant": {"epochMs": 1.5}})

# ---- check_availability ----
ev = lambda i, a, b, **k: {"id": i, "start": a, "end": b, **k}
add(
    "check_availability",
    "basic",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [ev("a", inst(2025, 1, 2, 10), inst(2025, 1, 2, 11))],
    },
)
add(
    "check_availability",
    "touching_coalesce",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [
            ev("a", inst(2025, 1, 2, 10), inst(2025, 1, 2, 11)),
            ev("b", inst(2025, 1, 2, 11), inst(2025, 1, 2, 12)),
        ],
    },
)
add("check_availability", "empty_events", {"window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)), "events": []})
add(
    "check_availability",
    "cancelled_no_occupy",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [ev("a", inst(2025, 1, 2, 10), inst(2025, 1, 2, 11), status="cancelled")],
    },
)
add(
    "check_availability",
    "free_no_occupy",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [ev("a", inst(2025, 1, 2, 10), inst(2025, 1, 2, 11), availability="free")],
    },
)
add(
    "check_availability",
    "tentative_default",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [ev("a", inst(2025, 1, 2, 10), inst(2025, 1, 2, 11), availability="tentative")],
    },
)
add(
    "check_availability",
    "tentative_as_busy",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [ev("a", inst(2025, 1, 2, 10), inst(2025, 1, 2, 11), availability="tentative")],
        "treatTentativeAsBusy": True,
    },
)
add(
    "check_availability",
    "zero_length",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [ev("a", inst(2025, 1, 2, 10), inst(2025, 1, 2, 10))],
    },
)
add("check_availability", "err_bad_interval", {"window": iv(inst(2025, 1, 2, 17), inst(2025, 1, 2, 9)), "events": []})

# ---- detect_conflicts ----
add(
    "detect_conflicts",
    "touching_none",
    {
        "events": [
            ev("a", inst(2025, 1, 1, 9), inst(2025, 1, 1, 10)),
            ev("b", inst(2025, 1, 1, 10), inst(2025, 1, 1, 11)),
        ]
    },
)
add(
    "detect_conflicts",
    "overlap_one",
    {
        "events": [
            ev("a", inst(2025, 1, 1, 9), inst(2025, 1, 1, 10)),
            ev("b", inst(2025, 1, 1, 9, 30), inst(2025, 1, 1, 10, 30)),
        ]
    },
)
add(
    "detect_conflicts",
    "three_events",
    {
        "events": [
            ev("a", inst(2025, 1, 1, 9), inst(2025, 1, 1, 11)),
            ev("b", inst(2025, 1, 1, 10), inst(2025, 1, 1, 12)),
            ev("c", inst(2025, 1, 1, 11, 30), inst(2025, 1, 1, 12, 30)),
        ]
    },
)
add(
    "detect_conflicts",
    "cancelled_excluded",
    {
        "events": [
            ev("a", inst(2025, 1, 1, 9), inst(2025, 1, 1, 11)),
            ev("b", inst(2025, 1, 1, 10), inst(2025, 1, 1, 12), status="cancelled"),
        ]
    },
)
add(
    "detect_conflicts",
    "window_clip",
    {
        "events": [
            ev("a", inst(2025, 1, 1, 9), inst(2025, 1, 1, 11)),
            ev("b", inst(2025, 1, 1, 10), inst(2025, 1, 1, 12)),
        ],
        "window": iv(inst(2025, 1, 1, 10, 30), inst(2025, 1, 1, 11, 30)),
    },
)
add("detect_conflicts", "empty", {"events": []})

# ---- find_slots ----
NYW = iv(inst(2025, 1, 2, 9, tz="America/New_York"), inst(2025, 1, 2, 17, tz="America/New_York"))
busy2 = [
    ev("m", inst(2025, 1, 2, 10, tz="America/New_York"), inst(2025, 1, 2, 11, tz="America/New_York")),
    ev("n", inst(2025, 1, 2, 14, tz="America/New_York"), inst(2025, 1, 2, 15, tz="America/New_York")),
]
add(
    "find_slots",
    "basic_60",
    {"timeZone": "America/New_York", "candidateWindows": [NYW], "events": busy2, "durationMinutes": 60},
)
add(
    "find_slots",
    "gran_30",
    {
        "timeZone": "America/New_York",
        "candidateWindows": [NYW],
        "events": busy2,
        "durationMinutes": 60,
        "constraints": {"granularityMinutes": 30},
    },
)
add(
    "find_slots",
    "buffers",
    {
        "timeZone": "America/New_York",
        "candidateWindows": [NYW],
        "events": busy2,
        "durationMinutes": 60,
        "constraints": {"bufferBeforeMinutes": 15, "bufferAfterMinutes": 15},
    },
)
add(
    "find_slots",
    "min_notice",
    {
        "timeZone": "America/New_York",
        "candidateWindows": [NYW],
        "events": busy2,
        "durationMinutes": 60,
        "now": inst(2025, 1, 2, 12, tz="America/New_York"),
        "constraints": {"minNoticeMinutes": 120},
    },
)
add(
    "find_slots",
    "max_slots",
    {"timeZone": "America/New_York", "candidateWindows": [NYW], "events": [], "durationMinutes": 30, "maxSlots": 3},
)
add(
    "find_slots",
    "empty_events",
    {"timeZone": "America/New_York", "candidateWindows": [NYW], "events": [], "durationMinutes": 120},
)
add(
    "find_slots",
    "business_hours",
    {
        "timeZone": "America/New_York",
        "candidateWindows": [
            iv(inst(2025, 1, 2, 0, tz="America/New_York"), inst(2025, 1, 4, 0, tz="America/New_York"))
        ],
        "events": [],
        "durationMinutes": 60,
        "dstPolicy": DP,
        "constraints": {"businessHours": [{"weekday": w, "start": "09:00", "end": "17:00"} for w in (1, 2, 3, 4, 5)]},
    },
)
add("find_slots", "err_missing_tz", {"candidateWindows": [NYW], "durationMinutes": 60})
add(
    "find_slots",
    "err_bh_no_dst",
    {
        "timeZone": "America/New_York",
        "candidateWindows": [NYW],
        "durationMinutes": 60,
        "constraints": {"businessHours": [{"weekday": 1, "start": "09:00", "end": "17:00"}]},
    },
)
add("find_slots", "err_invalid_tz", {"timeZone": "Nowhere/Nope", "candidateWindows": [NYW], "durationMinutes": 60})

# ---- create_event_plan (+ idempotency across serialization) ----
draft = {
    "id": "e1",
    "calendarId": "c",
    "timeZone": "America/New_York",
    "start": wall(2025, 1, 2, 9),
    "end": wall(2025, 1, 2, 10),
}
add("create_event_plan", "basic", {"calendarId": "c", "timeZone": "America/New_York", "dstPolicy": DP, "draft": draft})
# same content, different key order + reordered nested fields -> same idempotencyKey
draft_reordered = {
    "end": wall(2025, 1, 2, 10),
    "timeZone": "America/New_York",
    "calendarId": "c",
    "id": "e1",
    "start": wall(2025, 1, 2, 9),
}
add(
    "create_event_plan",
    "idem_reordered",
    {"dstPolicy": DP, "timeZone": "America/New_York", "calendarId": "c", "draft": draft_reordered},
)
add(
    "create_event_plan",
    "selected_slot",
    {
        "id": "e1",
        "calendarId": "c",
        "timeZone": "America/New_York",
        "selectedSlot": iv(inst(2025, 1, 2, 14), inst(2025, 1, 2, 15)),
    },
)
# rejectOnConflict -> CONFLICT_FOUND
add(
    "create_event_plan",
    "reject_on_conflict",
    {
        "id": "e1",
        "calendarId": "c",
        "timeZone": "America/New_York",
        "selectedSlot": iv(inst(2025, 1, 2, 14), inst(2025, 1, 2, 15)),
        "rejectOnConflict": True,
        "existing": [{"id": "x", "start": inst(2025, 1, 2, 14, 30), "end": inst(2025, 1, 2, 15, 30)}],
    },
)
# idempotency: differs from "basic" only by explicit defaults -> different inputHash, SAME idempotencyKey
add(
    "create_event_plan",
    "idem_explicit_default",
    {
        "calendarId": "c",
        "timeZone": "America/New_York",
        "dstPolicy": DP,
        "draft": {**draft, "status": "confirmed", "availability": "busy"},
    },
)
add("create_event_plan", "err_missing_dst", {"calendarId": "c", "timeZone": "America/New_York", "draft": draft})
add(
    "create_event_plan",
    "err_missing_draft_tz",
    {
        "calendarId": "c",
        "timeZone": "America/New_York",
        "dstPolicy": DP,
        "draft": {"id": "e1", "calendarId": "c", "start": wall(2025, 1, 2, 9), "end": wall(2025, 1, 2, 10)},
    },
)

# ---- reschedule_event_plan ----
ev_existing = {
    "id": "e1",
    "calendarId": "c",
    "timeZone": "America/New_York",
    "start": inst(2025, 1, 2, 14, tz="America/New_York"),
    "end": inst(2025, 1, 2, 15, tz="America/New_York"),
}
add(
    "reschedule_event_plan",
    "preserve_elapsed",
    {
        "event": ev_existing,
        "newStart": inst(2025, 1, 2, 16, tz="America/New_York"),
        "durationPolicy": "preserveElapsed",
    },
)
add(
    "reschedule_event_plan",
    "preserve_wallclock",
    {"event": ev_existing, "newStart": wall(2025, 3, 8, 14), "durationPolicy": "preserveWallClock", "dstPolicy": DP},
)
# cross-DST: preserveElapsed vs preserveWallClock differ (move across spring-forward)
add(
    "reschedule_event_plan",
    "cross_dst_elapsed",
    {"event": ev_existing, "newStart": wall(2025, 3, 9, 1, 30), "durationPolicy": "preserveElapsed", "dstPolicy": DP},
)
add("reschedule_event_plan", "err_missing_durpolicy", {"event": ev_existing, "newStart": inst(2025, 1, 2, 16)})

# ---- cancel_event_plan ----
cancel_ev = {
    "id": "e1",
    "calendarId": "c",
    "timeZone": "America/New_York",
    "start": inst(2025, 1, 2, 14, tz="America/New_York"),
    "end": inst(2025, 1, 2, 15, tz="America/New_York"),
}
add("cancel_event_plan", "tombstone", {"event": cancel_ev})
add(
    "cancel_event_plan",
    "single_occurrence",
    {"event": cancel_ev, "occurrenceStart": inst(2025, 1, 2, 14, tz="America/New_York")},
)
add("cancel_event_plan", "span_all", {"event": cancel_ev, "span": "all"})


# ---- expand_recurrence ----
def master(rule, **k):
    m = {
        "id": "m",
        "calendarId": "c",
        "start": wall(2025, 1, 1, 9),
        "end": wall(2025, 1, 1, 9, 30),
        "timeZone": "America/New_York",
        "recurrenceRule": rule,
    }
    m.update(k)
    return m


add(
    "expand_recurrence",
    "daily_count3",
    {"master": master({"frequency": "DAILY", "interval": 1, "count": 3, "wkst": 1}), "dstPolicy": DP},
)
add(
    "expand_recurrence",
    "weekly_byday",
    {
        "master": master(
            {"frequency": "WEEKLY", "count": 4, "byDay": [{"weekday": 1}, {"weekday": 3}, {"weekday": 5}], "wkst": 1}
        ),
        "dstPolicy": DP,
    },
)
add(
    "expand_recurrence",
    "monthly_bymonthday31",
    {
        "master": master(
            {"frequency": "MONTHLY", "count": 4, "byMonthDay": [31]},
            start=wall(2025, 1, 31, 9),
            end=wall(2025, 1, 31, 9, 30),
        ),
        "dstPolicy": DP,
    },
)
add(
    "expand_recurrence",
    "monthly_2nd_tuesday",
    {"master": master({"frequency": "MONTHLY", "count": 3, "byDay": [{"weekday": 2, "ordinal": 2}]}), "dstPolicy": DP},
)
add(
    "expand_recurrence",
    "monthly_last_weekday_bysetpos",
    {
        "master": master(
            {
                "frequency": "MONTHLY",
                "count": 3,
                "byDay": [{"weekday": 1}, {"weekday": 2}, {"weekday": 3}, {"weekday": 4}, {"weekday": 5}],
                "bySetPos": [-1],
            }
        ),
        "dstPolicy": DP,
    },
)
add("expand_recurrence", "yearly", {"master": master({"frequency": "YEARLY", "count": 3}), "dstPolicy": DP})
add(
    "expand_recurrence",
    "interval2_daily",
    {"master": master({"frequency": "DAILY", "interval": 2, "count": 4}), "dstPolicy": DP},
)
add(
    "expand_recurrence",
    "until",
    {"master": master({"frequency": "DAILY", "until": inst(2025, 1, 5, 14)}), "dstPolicy": DP},
)
add(
    "expand_recurrence",
    "exdate",
    {
        "master": master({"frequency": "DAILY", "count": 5}),
        "dstPolicy": DP,
        "exDates": [inst(2025, 1, 3, 9, tz="America/New_York")],
    },
)
add(
    "expand_recurrence",
    "window_clip",
    {
        "master": master({"frequency": "DAILY", "count": 10}),
        "dstPolicy": DP,
        "window": iv(inst(2025, 1, 3), inst(2025, 1, 6)),
    },
)
add("expand_recurrence", "limit", {"master": master({"frequency": "DAILY", "count": 100}), "dstPolicy": DP, "limit": 3})
add(
    "expand_recurrence",
    "override_replace",
    {
        "master": master({"frequency": "DAILY", "count": 3}),
        "dstPolicy": DP,
        "overrides": [
            {
                "recurrenceId": inst(2025, 1, 2, 9, tz="America/New_York"),
                "start": inst(2025, 1, 2, 14, tz="America/New_York"),
                "end": inst(2025, 1, 2, 15, tz="America/New_York"),
            }
        ],
    },
)
add(
    "expand_recurrence",
    "override_cancel",
    {
        "master": master({"frequency": "DAILY", "count": 3}),
        "dstPolicy": DP,
        "overrides": [
            {
                "recurrenceId": inst(2025, 1, 2, 9, tz="America/New_York"),
                "start": inst(2025, 1, 2, 9, tz="America/New_York"),
                "end": inst(2025, 1, 2, 9, 30, tz="America/New_York"),
                "status": "cancelled",
            }
        ],
    },
)
add(
    "expand_recurrence",
    "dst_spring_daily",
    {
        "master": master({"frequency": "DAILY", "count": 5}, start=wall(2025, 3, 7, 2, 30), end=wall(2025, 3, 7, 3)),
        "dstPolicy": {"gap": "earliest", "overlap": "earliest"},
    },
)
add("expand_recurrence", "err_unbounded", {"master": master({"frequency": "DAILY"}), "dstPolicy": DP})
add("expand_recurrence", "err_missing_dst", {"master": master({"frequency": "DAILY", "count": 3})})

# ---- next_occurrence ----
add(
    "next_occurrence",
    "daily",
    {
        "master": master({"frequency": "DAILY", "wkst": 1}),
        "dstPolicy": DP,
        "after": inst(2025, 1, 1, 12, tz="America/New_York"),
    },
)
add(
    "next_occurrence",
    "weekly",
    {
        "master": master({"frequency": "WEEKLY", "byDay": [{"weekday": 1}], "wkst": 1}),
        "dstPolicy": DP,
        "after": inst(2025, 1, 1, 12, tz="America/New_York"),
    },
)
add(
    "next_occurrence",
    "with_exdate",
    {
        "master": master({"frequency": "DAILY"}),
        "dstPolicy": DP,
        "after": inst(2025, 1, 1, 12, tz="America/New_York"),
        "exDates": [inst(2025, 1, 2, 9, tz="America/New_York")],
    },
)
add(
    "next_occurrence",
    "count_exhausted_null",
    {
        "master": master({"frequency": "DAILY", "count": 2}),
        "dstPolicy": DP,
        "after": inst(2025, 6, 1, tz="America/New_York"),
    },
)
add(
    "next_occurrence",
    "until_past_null",
    {"master": master({"frequency": "DAILY", "until": inst(2025, 1, 5)}), "dstPolicy": DP, "after": inst(2025, 6, 1)},
)

# ---- regression: edge cases surfaced by differential fuzzing against the reference ----
# check_availability clips busy[] to the window (partial-overlap clipped, fully-outside excluded)
add(
    "check_availability",
    "busy_clipped_to_window",
    {
        "window": iv(inst(2025, 1, 2, 9), inst(2025, 1, 2, 17)),
        "events": [
            ev("a", inst(2025, 1, 2, 8), inst(2025, 1, 2, 10)),
            ev("b", inst(2025, 1, 2, 16), inst(2025, 1, 2, 18)),
            ev("c", inst(2025, 1, 1, 0), inst(2025, 1, 1, 12)),
        ],
    },
)
# create_event_plan validates the resolved draft interval
add(
    "create_event_plan",
    "err_draft_end_before_start",
    {
        "calendarId": "c",
        "dstPolicy": DP,
        "draft": {
            "id": "e1",
            "calendarId": "c",
            "timeZone": "America/New_York",
            "start": wall(2025, 3, 10, 10),
            "end": wall(2025, 3, 10, 9),
        },
    },
)
# expand_recurrence validates override + window intervals
add(
    "expand_recurrence",
    "err_override_end_before_start",
    {
        "master": master({"frequency": "DAILY", "count": 3}),
        "dstPolicy": DP,
        "overrides": [
            {
                "recurrenceId": inst(2025, 1, 2, 9, tz="America/New_York"),
                "start": inst(2025, 1, 2, 15, tz="America/New_York"),
                "end": inst(2025, 1, 2, 14, tz="America/New_York"),
            }
        ],
    },
)
add(
    "expand_recurrence",
    "err_window_end_before_start",
    {
        "master": master({"frequency": "DAILY", "count": 5}),
        "dstPolicy": DP,
        "window": iv(inst(2025, 1, 5), inst(2025, 1, 1)),
    },
)
# find_slots: a min-notice floor inside the free region starts the first slot at the floor (not grid-aligned)
add(
    "find_slots",
    "min_notice_floor_in_region",
    {
        "timeZone": "America/New_York",
        "durationMinutes": 60,
        "candidateWindows": [
            iv(inst(2025, 1, 2, 9, tz="America/New_York"), inst(2025, 1, 2, 17, tz="America/New_York"))
        ],
        "now": inst(2025, 1, 2, 9, tz="America/New_York"),
        "constraints": {"minNoticeMinutes": 95},
    },
)
# recurrence COUNT counts RESOLVED occurrences: a DST-gap occurrence skipped under reject does not consume it
add(
    "expand_recurrence",
    "count_dst_gap_skip",
    {
        "dstPolicy": {"gap": "reject", "overlap": "reject"},
        "master": master(
            {"frequency": "HOURLY", "interval": 2, "byMonthDay": [1, 30], "count": 15},
            timeZone="Europe/Dublin",
            start=wall(2025, 2, 2, 1, 30),
            end=wall(2025, 2, 2, 2, 30),
        ),
    },
)
# an occurrence whose END wall lands in a DST overlap is kept (existence depends only on the start)
add(
    "expand_recurrence",
    "occurrence_end_in_dst_overlap",
    {
        "dstPolicy": {"gap": "latest", "overlap": "reject"},
        "master": master(
            {"frequency": "HOURLY", "byMonth": [6, 11], "count": 8},
            timeZone="America/Los_Angeles",
            start=wall(2026, 10, 1, 9),
            end=wall(2026, 10, 1, 10),
        ),
    },
)
add(
    "next_occurrence",
    "dst_overlap_end",
    {
        "dstPolicy": {"gap": "latest", "overlap": "reject"},
        "after": inst(2024, 12, 6),
        "master": master(
            {"frequency": "HOURLY", "byMonth": [6, 11], "count": 8},
            timeZone="America/Los_Angeles",
            start=wall(2026, 10, 1, 9),
            end=wall(2026, 10, 1, 10),
        ),
    },
)
# a never-satisfiable BY* constraint yields an empty set, not a hang
add(
    "expand_recurrence",
    "impossible_bymonthday_empty",
    {"master": master({"frequency": "MONTHLY", "byMonth": [2], "byMonthDay": [31], "count": 5}), "dstPolicy": DP},
)

# ---- generate ----
import shutil

if VEC.exists():
    shutil.rmtree(VEC)
counts: dict[str, int] = {}
for i, (op, label, payload) in enumerate(cases):
    expected = run(op, payload)
    d = VEC / op
    d.mkdir(parents=True, exist_ok=True)
    n = counts.get(op, 0)
    counts[op] = n + 1
    (d / f"{n:03d}_{label}.json").write_text(
        json.dumps({"op": op, "input": payload, "expected": expected}, indent=2) + "\n"
    )

total = sum(counts.values())
print(f"generated {total} vectors across {len(counts)} ops")
for op in sorted(counts):
    print(f"  {op}: {counts[op]}")
