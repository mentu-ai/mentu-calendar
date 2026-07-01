"""Time zones resolved from the pinned ``tzdata`` wheel only — never the host.

Reading each zone's TZif directly from the ``tzdata`` package (rather than the host's zoneinfo search
path) makes offsets deterministic and host-independent, and avoids mutating any global ``zoneinfo``
state — safe to import inside a larger application.
"""

from __future__ import annotations

import importlib.resources
import re
import zoneinfo
from functools import cache

from .errors import CalendarError

PINNED_TZDATA_VERSION = "2025b"
_ZONE_ID_RE = re.compile(r"^[A-Za-z0-9+_-]+(?:/[A-Za-z0-9+_-]+)*$")


def tzdata_version() -> str:
    """The IANA release the ``tzdata`` wheel provides; asserted to match the pin."""
    import tzdata

    found = tzdata.IANA_VERSION
    if found != PINNED_TZDATA_VERSION:
        raise RuntimeError(f"tzdata version mismatch: found {found!r}, expected {PINNED_TZDATA_VERSION!r}")
    return PINNED_TZDATA_VERSION


@cache
def get_zone(zone_id: str) -> zoneinfo.ZoneInfo:
    """Load ``zone_id`` from the pinned bundle, or raise ``INVALID_TIME_ZONE``."""
    if not _ZONE_ID_RE.match(zone_id):
        raise CalendarError("INVALID_TIME_ZONE", f"Unrecognized time zone id: {zone_id}", {"zoneId": zone_id})
    try:
        ref = importlib.resources.files("tzdata.zoneinfo").joinpath(*zone_id.split("/"))
        with ref.open("rb") as f:
            return zoneinfo.ZoneInfo.from_file(f, key=zone_id)
    except (FileNotFoundError, IsADirectoryError, ModuleNotFoundError, OSError, ValueError):
        raise CalendarError(
            "INVALID_TIME_ZONE",
            f"Time zone is not available in the vendored bundle: {zone_id}",
            {"zoneId": zone_id},
        ) from None
