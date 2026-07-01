"""Operation router: dispatch(op, input) -> response envelope. Never raises."""

from __future__ import annotations

from typing import Any

from .errors import OPERATION_NOT_IMPLEMENTED, UNKNOWN_OPERATION, CalendarError
from .meta import build_meta
from .ops import OPS

OPERATIONS = (
    "resolve_timezone",
    "check_availability",
    "detect_conflicts",
    "find_slots",
    "create_event_plan",
    "reschedule_event_plan",
    "cancel_event_plan",
    "expand_recurrence",
    "next_occurrence",
)


def dispatch(op: str, inp: Any) -> dict[str, Any]:
    """Run one operation and return a canonical ``{ok, result|error, meta}`` envelope."""
    try:
        fn = OPS.get(op)
        if fn is None:
            if op in OPERATIONS:
                raise CalendarError(OPERATION_NOT_IMPLEMENTED, f"Operation not implemented: {op}", {})
            raise CalendarError(UNKNOWN_OPERATION, f"Unknown operation: {op}", {})
        result, policy_version = fn(inp)
        return {"ok": True, "result": result, "meta": build_meta(policy_version)}
    except CalendarError as e:
        return {"ok": False, "error": e.to_error(), "meta": build_meta()}
    except Exception as e:  # noqa: BLE001 — any unexpected failure becomes a structured error
        return {
            "ok": False,
            "error": {"code": "SCHEMA_VALIDATION_ERROR", "message": str(e), "details": {}, "retryable": False},
            "meta": build_meta(),
        }
