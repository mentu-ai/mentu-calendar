"""Reproducible differential cross-checks against the public reference libraries.

An adopter does not have to trust the maintainer's correctness claims: this module recomputes the
expected answers **independently** — timezone resolution via the standard-library ``zoneinfo`` and
recurrence via a plain ``dateutil.rrule`` — and asserts the engine agrees over a seeded spread of
inputs. It runs offline against the pinned ``tzdata`` wheel, so results are deterministic. Run it with
``pytest``. This is the reproducible core of the "verify it yourself" claim in ``docs/ADOPTING.md``.
"""

from __future__ import annotations

import random
import zoneinfo
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule

from mentu_calendar import dispatch

# Resolve the reference zones from the pinned `tzdata` wheel, not the host's system tz database, so this
# cross-check uses the SAME IANA release (2025b) the engine does — deterministic and host-independent.
zoneinfo.reset_tzpath(to=[])

ZONES = [
    "UTC",
    "America/New_York",
    "America/Los_Angeles",
    "America/Mexico_City",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Kolkata",
    "Asia/Kathmandu",
    "Australia/Sydney",
    "Pacific/Auckland",
    "Pacific/Chatham",
    "Africa/Cairo",
]
# realistic post-1970 span (1990..2035) where IANA data is unambiguous
_LO, _HI = 631152000000, 2051222400000


def test_resolve_timezone_matches_zoneinfo() -> None:
    """instant -> {offsetSeconds, abbreviation, wall} must match zoneinfo's own resolution."""
    g = random.Random(20260702)
    checked = 0
    for _ in range(1500):
        zone = g.choice(ZONES)
        ms = g.randint(_LO, _HI)
        out = dispatch("resolve_timezone", {"zoneId": zone, "instant": {"epochMs": ms}})
        assert out["ok"], out
        r = out["result"]
        # independent reference: standard-library zoneinfo
        dt = datetime.fromtimestamp(ms // 1000, ZoneInfo(zone))
        assert r["offsetSeconds"] == int(dt.utcoffset().total_seconds()), (zone, ms)
        assert r["abbreviation"] == dt.tzname(), (zone, ms)
        assert r["wall"] == {
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second,
        }, (zone, ms)
        checked += 1
    assert checked == 1500


@pytest.mark.parametrize(
    "freq_name,freq", [("DAILY", DAILY), ("WEEKLY", WEEKLY), ("MONTHLY", MONTHLY), ("YEARLY", YEARLY)]
)
def test_expand_recurrence_matches_dateutil(freq_name: str, freq: int) -> None:
    """Occurrence start instants must match an independent dateutil.rrule + zoneinfo localization."""
    g = random.Random(hash(freq_name) & 0xFFFF)
    dp = {"gap": "earliest", "overlap": "earliest"}
    for _ in range(60):
        zone = g.choice(ZONES)
        y, mo, d, h = g.randint(2018, 2030), g.randint(1, 12), g.randint(1, 28), g.randint(0, 23)
        count = g.randint(1, 12)
        interval = g.randint(1, 3)
        master = {
            "id": "m",
            "calendarId": "c",
            "start": {"year": y, "month": mo, "day": d, "hour": h, "minute": 0, "second": 0},
            "end": {"year": y, "month": mo, "day": d, "hour": h, "minute": 30, "second": 0},
            "timeZone": zone,
            "recurrenceRule": {"frequency": freq_name, "interval": interval, "count": count},
        }
        out = dispatch("expand_recurrence", {"master": master, "dstPolicy": dp})
        assert out["ok"], out
        got = [o["startInstant"]["epochMs"] for o in out["result"]["occurrences"]]

        # Independent reference: dateutil for the nominal walls, zoneinfo for the instant. For an
        # UNAMBIGUOUS wall the two must agree exactly. A DST gap/overlap wall resolves by the engine's
        # explicit dstPolicy (which is NOT zoneinfo's fold=0), so those are locked by the conformance
        # vectors and skipped here. With gap/overlap = earliest the engine never drops an occurrence,
        # so `got` stays index-aligned with the nominal sequence.
        tz = ZoneInfo(zone)
        noms = list(rrule(freq, dtstart=datetime(y, mo, d, h, 0, 0), interval=interval, count=count))
        assert len(got) == len(noms), (freq_name, zone, master["start"])
        for i, dt in enumerate(noms):
            if dt.replace(tzinfo=tz, fold=0).utcoffset() != dt.replace(tzinfo=tz, fold=1).utcoffset():
                continue  # DST gap/overlap — policy-specific, validated by the conformance vectors
            assert got[i] == int(dt.replace(tzinfo=tz, fold=0).timestamp()) * 1000, (
                freq_name,
                zone,
                master["start"],
                i,
            )


def test_find_slots_grid_matches_naive_computation() -> None:
    """A simple find_slots (no events, no business hours) equals a plain granularity walk."""
    g = random.Random(7)
    for _ in range(200):
        zone = g.choice(ZONES)
        start = g.randint(_LO, _HI)
        span_h = g.choice([1, 4, 8])
        dur = g.choice([15, 30, 60])
        gran = g.choice([15, 30, 60])
        end = start + span_h * 3600000
        out = dispatch(
            "find_slots",
            {
                "timeZone": zone,
                "durationMinutes": dur,
                "candidateWindows": [{"start": {"epochMs": start}, "end": {"epochMs": end}}],
                "constraints": {"granularityMinutes": gran},
            },
        )
        assert out["ok"], out
        got = [s["start"]["epochMs"] for s in out["result"]["slots"]]
        expected, s = [], start
        while s + dur * 60000 <= end:
            expected.append(s)
            s += gran * 60000
        assert got == expected, (zone, start, span_h, dur, gran, got[:3], expected[:3])
