"""CLI surface.

  mentu-calendar call <op> [--input file.json]   # or JSON on stdin
  mentu-calendar --schema [op]                    # JSON request schema(s)
  mentu-calendar --self-test                      # deterministic self-check
  mentu-calendar --version

Exit codes: 0 success, 1 operation error (ok:false), 2 CLI/input error.
"""

from __future__ import annotations

import importlib.resources
import json
import sys

from .canonical import canonical_json
from .dispatch import OPERATIONS, dispatch
from .meta import ENGINE_VERSION, build_meta


def _load_schema(op: str) -> dict:
    ref = importlib.resources.files("mentu_calendar.schemas").joinpath(f"{op}.schema.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _self_test() -> int:
    inp = {"zoneId": "America/New_York", "instant": {"epochMs": 1736942400000}}
    a = canonical_json(dispatch("resolve_timezone", inp))
    b = canonical_json(dispatch("resolve_timezone", inp))
    deterministic = a == b
    meta = build_meta()
    pinned = meta["tzdata"] == "2025b"
    dispatchable = all("ok" in dispatch(op, {}) for op in OPERATIONS)
    ok = deterministic and pinned and dispatchable
    sys.stdout.write(
        f"{'PASS' if ok else 'FAIL'} self-test "
        f"(deterministic={str(deterministic).lower()}, tzdata={meta['tzdata']}, operations={str(dispatchable).lower()})\n"
    )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--version" in args:
        sys.stdout.write(ENGINE_VERSION + "\n")
        return 0
    if "--self-test" in args:
        return _self_test()
    if "--schema" in args:
        i = args.index("--schema")
        op = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else None
        if op is not None:
            if op not in OPERATIONS:
                sys.stderr.write(f"error: no schema for operation: {op}\n")
                return 2
            sys.stdout.write(canonical_json(_load_schema(op)) + "\n")
        else:
            sys.stdout.write(canonical_json({"schemas": {o: _load_schema(o) for o in OPERATIONS}}) + "\n")
        return 0
    if args and args[0] == "call":
        op = args[1] if len(args) > 1 else None
        if not op:
            sys.stderr.write("error: missing operation\n")
            return 2
        try:
            if "--input" in args:
                with open(args[args.index("--input") + 1], encoding="utf-8") as f:
                    text = f.read()
            else:
                text = sys.stdin.read()
            inp = json.loads(text)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"error: {e}\n")
            return 2
        out = dispatch(op, inp)
        sys.stdout.write(canonical_json(out) + "\n")
        return 0 if out.get("ok") else 1

    sys.stderr.write("usage: mentu-calendar call <op> [--input file] | --schema [op] | --self-test | --version\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
