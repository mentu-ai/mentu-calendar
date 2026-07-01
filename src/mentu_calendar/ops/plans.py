"""create / reschedule / cancel event plans. Plans are diffs; a provider adapter does live writes.

planId = sha256(canonical(resolved-plan)); idempotencyKey = planId; inputHash = sha256(canonical(input)).
"""

from __future__ import annotations

from typing import Any

from ..canonical import sha256_canonical
from ..errors import CalendarError
from ..intervals import as_ms, conflict_occupies, strict_overlap, to_interval
from ..temporal import (
    epoch_sec_to_wall,
    instant_to_wall,
    validate_dst_policy,
    validate_wall,
    wall_to_epoch_sec,
    wall_to_instant,
)

DEFAULT_PROFILE = "default"
DEFAULT_POLICY_VERSION = "2026.1"


def _req_str(v: Any, name: str) -> str:
    if not isinstance(v, str) or v == "":
        raise CalendarError("SCHEMA_VALIDATION_ERROR", f"{name} must be a string", {})
    return v


def _as_instant(v: Any) -> dict[str, int]:
    if not isinstance(v, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "instant must be an object", {})
    ems = v.get("epochMs")
    if not isinstance(ems, int) or isinstance(ems, bool):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "instant.epochMs must be an integer", {})
    return {"epochMs": ems}


def _is_wall(v: Any) -> bool:
    return isinstance(v, dict) and "year" in v


def _plan_hashes(op_obj: dict[str, Any], inp: Any) -> tuple[str, str, str]:
    plan_id = sha256_canonical(op_obj)
    return plan_id, sha256_canonical(inp), plan_id


def _wrap(plan: dict[str, Any], conflicts: list | None = None) -> tuple[dict[str, Any], str]:
    result: dict[str, Any] = {"plan": plan, "policyProfile": DEFAULT_PROFILE, "policyVersion": DEFAULT_POLICY_VERSION}
    if conflicts is not None:
        result["conflicts"] = conflicts
    return result, DEFAULT_POLICY_VERSION


def _conflicts(event: dict[str, Any], existing: list) -> list[dict[str, Any]]:
    if not conflict_occupies(event):
        return []
    a_iv = (event["start"]["epochMs"], event["end"]["epochMs"])
    out: list[dict[str, Any]] = []
    for e in existing:
        if not conflict_occupies(e):
            continue
        ov = strict_overlap(a_iv, (e["start"]["epochMs"], e["end"]["epochMs"]))
        if ov is not None:
            a, b = (event["id"], e["id"]) if event["id"] <= e["id"] else (e["id"], event["id"])
            out.append({"a": a, "b": b, "overlap": to_interval(*ov)})
    out.sort(key=lambda c: (c["a"], c["b"], c["overlap"]["start"]["epochMs"], c["overlap"]["end"]["epochMs"]))
    return out


def create_event_plan(inp: Any) -> tuple[dict[str, Any], str | None]:
    has_draft = "draft" in inp
    has_slot = "selectedSlot" in inp
    if has_draft == has_slot:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "Provide exactly one of `draft` or `selectedSlot`", {})

    if has_draft:
        gap, overlap = validate_dst_policy(inp.get("dstPolicy"))
        draft = inp["draft"]
        did = _req_str(draft.get("id"), "draft.id")
        dcal = _req_str(draft.get("calendarId"), "draft.calendarId")
        dtz = _req_str(draft.get("timeZone"), "draft.timeZone")
        si = wall_to_instant(dtz, validate_wall(draft["start"]), gap, overlap)["instant"]["epochMs"]
        ei = wall_to_instant(dtz, validate_wall(draft["end"]), gap, overlap)["instant"]["epochMs"]
        if ei < si:
            raise CalendarError(
                "INVALID_INTERVAL",
                "Interval end must not precede its start",
                {"interval": {"start": {"epochMs": si}, "end": {"epochMs": ei}}},
            )
        event = {
            "id": did,
            "calendarId": dcal,
            "start": {"epochMs": si},
            "end": {"epochMs": ei},
            "isAllDay": bool(draft.get("isAllDay", False)),
            "status": draft.get("status", "confirmed"),
            "availability": draft.get("availability", "busy"),
            "timeZone": dtz,
        }
    else:
        eid = _req_str(inp.get("id"), "id")
        ecal = _req_str(inp.get("calendarId"), "calendarId")
        si, ei = as_ms(inp["selectedSlot"])
        event = {
            "id": eid,
            "calendarId": ecal,
            "start": {"epochMs": si},
            "end": {"epochMs": ei},
            "isAllDay": bool(inp.get("isAllDay", False)),
            "status": inp.get("status", "confirmed"),
            "availability": inp.get("availability", "busy"),
        }
        if inp.get("timeZone") is not None:
            event["timeZone"] = inp["timeZone"]

    conflicts = None
    if inp.get("validateConflicts") or inp.get("rejectOnConflict"):
        conflicts = _conflicts(event, inp.get("existing", []))
        if inp.get("rejectOnConflict") and conflicts:
            raise CalendarError(
                "CONFLICT_FOUND",
                f"Planned event conflicts with {len(conflicts)} existing event(s)",
                {"conflicts": conflicts},
            )

    plan_id, input_hash, idem = _plan_hashes({"op": "create", "event": event}, inp)
    plan = {"op": "create", "planId": plan_id, "inputHash": input_hash, "idempotencyKey": idem, "event": event}
    return _wrap(plan, conflicts)


def reschedule_event_plan(inp: Any) -> tuple[dict[str, Any], str | None]:
    dur = inp.get("durationPolicy")
    if dur is None:
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "durationPolicy is required", {})
    if dur not in ("preserveElapsed", "preserveWallClock"):
        raise CalendarError(
            "SCHEMA_VALIDATION_ERROR", "durationPolicy must be 'preserveElapsed' or 'preserveWallClock'", {}
        )
    span = inp.get("span", "thisEvent")
    event = inp.get("event")
    if not isinstance(event, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "event is required", {})
    eid = _req_str(event.get("id"), "event.id")
    ev_start, ev_end = event["start"]["epochMs"], event["end"]["epochMs"]
    tz = event.get("timeZone")
    new_start = inp.get("newStart")

    if _is_wall(new_start):
        if not isinstance(tz, str):
            raise CalendarError("MISSING_TIME_ZONE", "event.timeZone is required to resolve a wall-clock newStart", {})
        gap, overlap = validate_dst_policy(inp.get("dstPolicy"))
        ns_ms = wall_to_instant(tz, validate_wall(new_start), gap, overlap)["instant"]["epochMs"]
    else:
        ns_ms = _as_instant(new_start)["epochMs"]

    if dur == "preserveElapsed":
        ne_ms = ns_ms + (ev_end - ev_start)
    else:
        if not isinstance(tz, str):
            raise CalendarError("MISSING_TIME_ZONE", "event.timeZone is required for preserveWallClock", {})
        gap, overlap = validate_dst_policy(inp.get("dstPolicy"))
        delta = wall_to_epoch_sec(instant_to_wall(tz, ev_end)["wall"]) - wall_to_epoch_sec(
            instant_to_wall(tz, ev_start)["wall"]
        )
        ns_wall = instant_to_wall(tz, ns_ms)["wall"]
        ne_wall = epoch_sec_to_wall(wall_to_epoch_sec(ns_wall) + delta)
        ne_ms = wall_to_instant(tz, ne_wall, gap, overlap)["instant"]["epochMs"]

    resched = {
        "id": eid,
        "start": {"epochMs": ns_ms},
        "end": {"epochMs": ne_ms},
        "originalStart": {"epochMs": ev_start},
    }
    if "calendarId" in event:
        resched["calendarId"] = event["calendarId"]
    if tz is not None:
        resched["timeZone"] = tz
    events = [resched]

    plan_id, input_hash, idem = _plan_hashes(
        {"op": "update", "span": span, "durationPolicy": dur, "events": events}, inp
    )
    plan = {
        "op": "update",
        "planId": plan_id,
        "inputHash": input_hash,
        "idempotencyKey": idem,
        "span": span,
        "durationPolicy": dur,
        "events": events,
    }
    return _wrap(plan)


def cancel_event_plan(inp: Any) -> tuple[dict[str, Any], str | None]:
    span = inp.get("span", "thisEvent")
    event = inp.get("event")
    if not isinstance(event, dict):
        raise CalendarError("SCHEMA_VALIDATION_ERROR", "event is required", {})
    eid = _req_str(event.get("id"), "event.id")
    ecal = _req_str(event.get("calendarId"), "event.calendarId")
    norm = {
        "id": eid,
        "calendarId": ecal,
        "start": _as_instant(event["start"]),
        "end": _as_instant(event["end"]),
        "isAllDay": bool(event.get("isAllDay", False)),
        "status": event.get("status", "confirmed"),
        "availability": event.get("availability", "busy"),
    }
    if "timeZone" in event:
        norm["timeZone"] = event["timeZone"]

    if span == "thisEvent" and inp.get("occurrenceStart") is not None:
        exdate = [_as_instant(inp["occurrenceStart"])]
        op_obj = {"op": "cancel", "span": span, "event": norm, "exdate": exdate}
        plan_id, input_hash, idem = _plan_hashes(op_obj, inp)
        plan = {
            "op": "cancel",
            "planId": plan_id,
            "inputHash": input_hash,
            "idempotencyKey": idem,
            "span": span,
            "event": norm,
            "exdate": exdate,
        }
    else:
        norm = {**norm, "status": "cancelled"}
        op_obj = {"op": "cancel", "span": span, "event": norm}
        plan_id, input_hash, idem = _plan_hashes(op_obj, inp)
        plan = {
            "op": "cancel",
            "planId": plan_id,
            "inputHash": input_hash,
            "idempotencyKey": idem,
            "span": span,
            "event": norm,
        }
    return _wrap(plan)
