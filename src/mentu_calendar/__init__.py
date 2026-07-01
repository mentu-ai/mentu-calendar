"""Deterministic, offline, host-independent calendar scheduling engine.

A clean-room implementation of RFC 5545 recurrence, RFC 8536 (TZif) time-zone handling, and IANA
tzdata, with byte-identical output, explicit ``now``, explicit time zones, and half-open intervals.
"""

from __future__ import annotations

from .dispatch import OPERATIONS, dispatch
from .meta import ENGINE_VERSION as __version__

__all__ = ["dispatch", "OPERATIONS", "__version__"]
