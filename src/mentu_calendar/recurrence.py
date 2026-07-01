"""RFC 5545 recurrence expansion.

Occurrences are generated as fixed **local** wall times (via ``dateutil.rrule`` over a naive DTSTART)
and each is resolved to an instant through the zone + DST policy — so ``09:00 daily`` stays 09:00
local across DST. dateutil is an independent RFC 5545 implementation; the conformance vectors bind
the exact behavior.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from dateutil.rrule import DAILY, HOURLY, MINUTELY, MONTHLY, SECONDLY, WEEKLY, YEARLY, rrule
from dateutil.rrule import weekday as _weekday

from .errors import CalendarError
from .temporal import epoch_sec_to_wall, wall_to_epoch_sec, wall_to_instant

_FREQ = {
    "SECONDLY": SECONDLY,
    "MINUTELY": MINUTELY,
    "HOURLY": HOURLY,
    "DAILY": DAILY,
    "WEEKLY": WEEKLY,
    "MONTHLY": MONTHLY,
    "YEARLY": YEARLY,
}
_BY = [
    ("byMonth", "bymonth"),
    ("byMonthDay", "bymonthday"),
    ("byYearDay", "byyearday"),
    ("byWeekNo", "byweekno"),
    ("byHour", "byhour"),
    ("byMinute", "byminute"),
    ("bySecond", "bysecond"),
    ("bySetPos", "bysetpos"),
]
_HARD_CAP = 200_000
_HORIZON_YEARS = 400
_MAX_SEARCH_YEARS = 550  # rrule search horizon: bounds never-satisfiable BY* rules (won't scan to 9999)
_MAX_OCCURRENCES = 100_000  # materialized-occurrence ceiling (DoS bound)


def _build_rrule(master: dict[str, Any]) -> rrule:
    rule = master.get("recurrenceRule")
    if not isinstance(rule, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "master.recurrenceRule is required", {})
    freq_name = rule.get("frequency")
    freq = _FREQ.get(freq_name) if isinstance(freq_name, str) else None
    if freq is None:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "recurrenceRule.frequency is invalid", {"frequency": freq_name})
    s = master["start"]
    kwargs: dict[str, Any] = {
        "freq": freq,
        "dtstart": datetime(s["year"], s["month"], s["day"], s["hour"], s["minute"], s["second"]),
        "interval": rule.get("interval", 1),
    }
    # COUNT is applied in expand()/next_after() over RESOLVED occurrences, not here: a DST-gap
    # occurrence skipped under a reject policy must not consume the count (the series still yields
    # COUNT valid instances). So rrule is generated unbounded-but-horizon-capped.
    # Search horizon: bound the rrule scan so a never-satisfiable BY* constraint (e.g.
    # BYMONTH=2;BYMONTHDAY=31) cannot iterate to dateutil's year-9999 ceiling. Valid rules reach
    # their COUNT/UNTIL/window well before this; dateutil accepts count+until together.
    dtstart = kwargs["dtstart"]
    kwargs["until"] = datetime(min(dtstart.year + _MAX_SEARCH_YEARS, 9999), 12, 31, 23, 59, 59)
    # RFC 5545: WKST defaults to MO. Pin it explicitly on EVERY rule — dateutil defaults an
    # absent wkst to the mutable global calendar.firstweekday(), which would make WEEKLY;INTERVAL>1
    # and BYWEEKNO expansion depend on host/library state (non-deterministic). ISO 1..7 -> dateutil 0..6.
    kwargs["wkst"] = (rule["wkst"] - 1) if "wkst" in rule else 0
    if "byDay" in rule:
        kwargs["byweekday"] = [_weekday(d["weekday"] - 1, d.get("ordinal")) for d in rule["byDay"]]
    for src, dst in _BY:
        if src in rule:
            kwargs[dst] = rule[src]
    return rrule(**kwargs)


def _iter_nominal(master: dict[str, Any], gap: str, overlap: str) -> Iterator[tuple[int, int]]:
    """Yield (startInstant_ms, endInstant_ms) for each nominal occurrence, skipping DST-rejected ones."""
    tz = master["timeZone"]
    wall_dur = wall_to_epoch_sec(master["end"]) - wall_to_epoch_sec(master["start"])
    # An occurrence exists iff its START resolves; its END is always resolvable, so the reject policy
    # is downgraded there (a reject-overlap end takes earliest, a reject-gap end takes latest).
    end_gap = "latest" if gap == "reject" else gap
    end_overlap = "earliest" if overlap == "reject" else overlap
    try:
        it = iter(_build_rrule(master))
    except ValueError as e:
        # dateutil rejects some BY* combinations ("generates an empty set") at construction.
        raise CalendarError(
            "SCHEMA_VALIDATION_ERROR", "recurrenceRule does not produce a valid occurrence set", {}
        ) from e
    while True:
        try:
            dt = next(it)
        except StopIteration:
            return
        except ValueError as e:
            # ... or during iteration; surface a clean, structured error either way.
            raise CalendarError(
                "SCHEMA_VALIDATION_ERROR", "recurrenceRule does not produce a valid occurrence set", {}
            ) from e
        start_wall = {
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second,
        }
        try:
            si = wall_to_instant(tz, start_wall, gap, overlap)["instant"]["epochMs"]
        except CalendarError as e:
            if e.code in ("NONEXISTENT_WALL_TIME", "AMBIGUOUS_WALL_TIME"):
                continue  # the occurrence's START does not exist / is ambiguous under reject -> skipped
            raise
        end_wall = epoch_sec_to_wall(wall_to_epoch_sec(start_wall) + wall_dur)
        ei = wall_to_instant(tz, end_wall, end_gap, end_overlap)["instant"]["epochMs"]
        yield si, ei


def _occurrence(
    master: dict[str, Any], si: int, ei: int, orig: int, source: str, id_: str | None = None, cal: str | None = None
) -> dict[str, Any]:
    return {
        "id": id_ or master["id"],
        "calendarId": cal or master["calendarId"],
        "startInstant": {"epochMs": si},
        "endInstant": {"epochMs": ei},
        "originalStart": {"epochMs": orig},
        "source": source,
    }


def expand(
    master: dict[str, Any],
    gap: str,
    overlap: str,
    ex_dates: list,
    overrides: list,
    window: tuple[int, int] | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    rule = master["recurrenceRule"]
    count = rule.get("count")
    until_ms = rule["until"]["epochMs"] if "until" in rule else None
    if count is None and until_ms is None and window is None and limit is None:
        raise CalendarError(
            "UNBOUNDED_RECURRENCE",
            "Recurrence has no terminating bound: provide COUNT, UNTIL, a window, or a limit",
            {},
        )

    occ: list[dict[str, Any]] = []
    series = 0  # resolved series occurrences (DST-gap/overlap skips already excluded by _iter_nominal)
    for i, (si, ei) in enumerate(_iter_nominal(master, gap, overlap)):
        if i >= _HARD_CAP:
            raise CalendarError("RECURRENCE_LIMIT_EXCEEDED", "Recurrence exceeded the generation cap", {})
        if until_ms is not None and si > until_ms:
            break
        # window bounds the series only when nothing else terminates it (no COUNT / no UNTIL)
        if count is None and until_ms is None and window is not None and si >= window[1]:
            break
        series += 1
        if window is None or (window[0] <= si < window[1]):
            occ.append(_occurrence(master, si, ei, si, "recurrence"))
            if len(occ) >= _MAX_OCCURRENCES:
                raise CalendarError(
                    "RECURRENCE_LIMIT_EXCEEDED",
                    f"Recurrence expansion exceeded the maximum of {_MAX_OCCURRENCES} occurrences",
                    {},
                )
        if count is not None and series >= count:
            break
        if count is None and until_ms is None and window is None and limit is not None and series >= limit:
            break

    ex = {e["epochMs"] for e in ex_dates}
    occ = [o for o in occ if o["originalStart"]["epochMs"] not in ex]

    ov_by_rid = {o["recurrenceId"]["epochMs"]: o for o in overrides}
    materialized: list[dict[str, Any]] = []
    for o in occ:
        rid = o["originalStart"]["epochMs"]
        ov = ov_by_rid.get(rid)
        if ov is None:
            materialized.append(o)
        elif ov.get("status") != "cancelled":
            materialized.append(
                _occurrence(
                    master,
                    ov["start"]["epochMs"],
                    ov["end"]["epochMs"],
                    rid,
                    "override",
                    ov.get("id"),
                    ov.get("calendarId"),
                )
            )

    if limit is not None:
        materialized = materialized[:limit]
    materialized.sort(key=lambda o: o["startInstant"]["epochMs"])
    return materialized


def next_after(master: dict[str, Any], gap: str, overlap: str, ex_dates: list, after_ms: int) -> dict[str, Any] | None:
    rule = master["recurrenceRule"]
    count = rule.get("count")
    until_ms = rule["until"]["epochMs"] if "until" in rule else None
    ex = {e["epochMs"] for e in ex_dates}
    horizon = wall_to_epoch_sec(master["start"]) * 1000 + _HORIZON_YEARS * 365 * 86400 * 1000
    series = 0  # resolved series occurrences (DST-gap/overlap skips already excluded)
    for i, (si, ei) in enumerate(_iter_nominal(master, gap, overlap)):
        if i >= _HARD_CAP or si > horizon:
            return None
        if until_ms is not None and si > until_ms:
            return None
        series += 1
        if si > after_ms and si not in ex:
            return _occurrence(master, si, ei, si, "recurrence")
        if count is not None and series >= count:
            return None  # series exhausted before any occurrence after `after`
    return None
