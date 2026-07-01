"""Every conformance vector must reproduce, byte-for-byte (except meta.engineVersion)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mentu_calendar import dispatch

VEC = Path(__file__).resolve().parent.parent / "conformance" / "vectors"
VECTORS = sorted(VEC.rglob("*.json"))


def _norm(x):
    if isinstance(x, dict):
        d = {k: _norm(v) for k, v in x.items()}
        m = d.get("meta")
        if isinstance(m, dict) and "engineVersion" in m:
            d["meta"] = {**m, "engineVersion": "<impl>"}
        return d
    if isinstance(x, list):
        return [_norm(v) for v in x]
    return x


def _canon(x) -> str:
    return json.dumps(_norm(x), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@pytest.mark.parametrize("vec_path", VECTORS, ids=lambda p: str(p.relative_to(VEC)))
def test_vector(vec_path: Path) -> None:
    vec = json.loads(vec_path.read_text())
    assert _canon(dispatch(vec["op"], vec["input"])) == _canon(vec["expected"])


def test_vectors_present() -> None:
    assert len(VECTORS) >= 140
