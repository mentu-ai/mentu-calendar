"""Operation registry: op name -> callable(input) -> (result, policy_version|None)."""

from __future__ import annotations

from .availability import check_availability, detect_conflicts, find_slots
from .plans import cancel_event_plan, create_event_plan, reschedule_event_plan
from .recurrence import expand_recurrence, next_occurrence
from .timezone import resolve_timezone

OPS = {
    "resolve_timezone": resolve_timezone,
    "check_availability": check_availability,
    "detect_conflicts": detect_conflicts,
    "find_slots": find_slots,
    "create_event_plan": create_event_plan,
    "reschedule_event_plan": reschedule_event_plan,
    "cancel_event_plan": cancel_event_plan,
    "expand_recurrence": expand_recurrence,
    "next_occurrence": next_occurrence,
}
