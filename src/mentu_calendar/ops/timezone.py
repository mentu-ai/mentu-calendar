"""resolve_timezone — instant <-> wall in a time zone, DST-policy aware."""

from __future__ import annotations

from typing import Any

from ..errors import CalendarError
from ..temporal import instant_to_wall, validate_dst_policy, validate_wall, wall_to_instant


def _as_instant(v: Any) -> dict[str, int]:
    if not isinstance(v, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "instant must be an object", {})
    ems = v.get("epochMs")
    if not isinstance(ems, int) or isinstance(ems, bool):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "instant.epochMs must be an integer", {})
    return {"epochMs": ems}


def resolve_timezone(inp: Any) -> tuple[dict[str, Any], str | None]:
    if not isinstance(inp, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "input must be an object", {})
    zone_id = inp.get("zoneId")
    if zone_id is None or zone_id == "":
        raise CalendarError("MISSING_TIME_ZONE", "zoneId is required", {})
    if not isinstance(zone_id, str):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "zoneId must be a string", {})

    has_wall = "wall" in inp
    has_instant = "instant" in inp
    if has_wall == has_instant:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "Provide exactly one of `wall` or `instant`", {})

    if has_wall:
        gap, overlap = validate_dst_policy(inp.get("dstPolicy"))
        wall = validate_wall(inp["wall"])
        r = wall_to_instant(zone_id, wall, gap, overlap)
        back = instant_to_wall(zone_id, r["instant"]["epochMs"])
        return {
            "instant": r["instant"],
            "wall": back["wall"],
            "offsetSeconds": r["offsetSeconds"],
            "abbreviation": r["abbreviation"],
            "fold": r["fold"],
            "resolution": r["resolution"],
        }, None

    inst = _as_instant(inp["instant"])
    reading = instant_to_wall(zone_id, inst["epochMs"])
    return {
        "instant": inst,
        "wall": reading["wall"],
        "offsetSeconds": reading["offsetSeconds"],
        "abbreviation": reading["abbreviation"],
        "fold": 0,
        "resolution": "exact",
    }, None
