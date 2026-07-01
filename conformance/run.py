#!/usr/bin/env python3
"""Run the conformance vectors against an engine and report pass/fail.

Default target: the local `mentu_calendar` package (`from mentu_calendar import dispatch`).
`--oracle "<cmd prefix>"`: compare against a CLI engine (invoked as `<cmd> call <op>`, JSON on stdin).

The comparison locks the ENTIRE response envelope EXCEPT `meta.engineVersion`, which is legitimately
implementation-specific. Both sides are re-serialized canonically, so any implementation reproducing
the specified values passes regardless of its own serialization.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VEC = ROOT / "conformance" / "vectors"


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


def canon(x) -> str:
    return json.dumps(_norm(x), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def get_target(oracle: str | None):
    if oracle:
        argv = shlex.split(oracle)

        def call(op, inp):
            p = subprocess.run(argv + ["call", op], input=json.dumps(inp), capture_output=True, text=True)
            return json.loads(p.stdout)

        return call
    sys.path.insert(0, str(ROOT / "src"))
    from mentu_calendar import dispatch  # noqa: E402

    return lambda op, inp: dispatch(op, inp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", help="CLI engine command prefix; default targets the local package")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    call = get_target(args.oracle)

    vectors = sorted(VEC.rglob("*.json"))
    npass = nfail = 0
    fails = []
    for f in vectors:
        vec = json.loads(f.read_text())
        expected = canon(vec["expected"])
        try:
            actual = canon(call(vec["op"], vec["input"]))
        except Exception as e:  # noqa: BLE001
            actual = f"<exception: {type(e).__name__}: {e}>"
        if actual == expected:
            npass += 1
        else:
            nfail += 1
            fails.append((f.relative_to(VEC), expected, actual))

    print(f"conformance: {npass} passed, {nfail} failed  ({len(vectors)} vectors)")
    for rel, exp, act in fails[:40]:
        print(f"  FAIL {rel}")
        if args.verbose:
            print(f"    expected: {exp[:400]}")
            print(f"    actual:   {act[:400]}")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
