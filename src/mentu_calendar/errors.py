"""Structured error model. All errors are deterministic, so ``retryable`` is always ``False``."""

from __future__ import annotations

from typing import Any

# Operation-level taxonomy (spec §Error model).
ERROR_CODES = frozenset(
    {
        "SCHEMA_VALIDATION_ERROR",
        "INVALID_INTERVAL",
        "INVALID_TIME_ZONE",
        "MISSING_TIME_ZONE",
        "MISSING_DST_POLICY",
        "NONEXISTENT_WALL_TIME",
        "AMBIGUOUS_WALL_TIME",
        "UNBOUNDED_RECURRENCE",
        "RECURRENCE_LIMIT_EXCEEDED",
        "NO_VALID_SLOT",
        "CONFLICT_FOUND",
        "STALE_OVERRIDE",
        "INPUT_TOO_LARGE",
        "MAX_EVENTS_EXCEEDED",
        "MAX_CALENDARS_EXCEEDED",
        "MAX_WINDOW_EXCEEDED",
    }
)
# Dispatch-level codes.
UNKNOWN_OPERATION = "UNKNOWN_OPERATION"
OPERATION_NOT_IMPLEMENTED = "OPERATION_NOT_IMPLEMENTED"


class CalendarError(Exception):
    """A structured, deterministic error carrying a stable code + machine-readable details."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details or {}
        self.retryable = False

    def to_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }
