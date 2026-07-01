"""Response metadata. ``engine`` names the stable contract family; ``engineVersion`` is this build."""

from __future__ import annotations

from typing import Any

from .tz import tzdata_version

SCHEMA_VERSION = "0.1"
ENGINE = "calendar-tool"
ENGINE_VERSION = "0.1.0"
DEFAULT_POLICY_VERSION = "2026.1"
ICU = "none"


def build_meta(policy_version: str | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "engine": ENGINE,
        "engineVersion": ENGINE_VERSION,
        "policyVersion": policy_version or DEFAULT_POLICY_VERSION,
        "tzdata": tzdata_version(),
        "icu": ICU,
    }
