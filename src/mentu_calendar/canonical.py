"""Canonical JSON — deterministic, byte-stable serialization.

Object keys are sorted lexicographically (recursively); arrays keep producer order; numbers are
emitted as integers where they are integral; ``-0`` normalizes to ``0``; non-finite numbers and
non-JSON values are rejected. There is no insignificant whitespace. See spec §Canonical JSON.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _normalize(v: Any) -> Any:
    # bool must precede int (bool is a subclass of int in Python).
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("non-finite numbers are not representable in canonical JSON")
        if v == 0:
            return 0
        return int(v) if v.is_integer() else v
    if isinstance(v, dict):
        return {k: _normalize(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_normalize(x) for x in v]
    raise TypeError(f"unsupported value in canonical JSON: {type(v).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize ``value`` to canonical JSON (sorted keys, no whitespace, integer numbers)."""
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_canonical(value: Any) -> str:
    """Hex SHA-256 of the canonical JSON bytes of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
