"""Stdio MCP server exposing the nine calendar operations as tools.

Dependency-free JSON-RPC 2.0 over newline-delimited stdin/stdout (the MCP stdio transport). Each
operation is a tool whose ``inputSchema`` is its published JSON Schema; ``tools/call`` runs
``dispatch`` and returns the canonical response envelope as text content. Pure and offline, like the
rest of the engine — no network, no ambient state.

Run:  ``mentu-calendar-mcp``  (or ``python -m mentu_calendar.mcp``)
"""

from __future__ import annotations

import importlib.resources
import json
import sys
from typing import Any, TextIO

from .dispatch import OPERATIONS, dispatch
from .meta import ENGINE_VERSION

PROTOCOL_VERSION = "2025-06-18"


def _schema(op: str) -> dict[str, Any]:
    ref = importlib.resources.files("mentu_calendar.schemas").joinpath(f"{op}.schema.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _input_schema(op: str) -> dict[str, Any]:
    # Keep $defs (needed for $ref), drop the $id/$schema meta-keys that some MCP clients reject.
    return {k: v for k, v in _schema(op).items() if k == "$defs" or not k.startswith("$")}


def _tools() -> list[dict[str, Any]]:
    return [
        {"name": op, "description": _schema(op).get("description", op), "inputSchema": _input_schema(op)}
        for op in OPERATIONS
    ]


def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message; return a response dict, or None for notifications."""
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mentu-calendar", "version": ENGINE_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": _tools()}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in OPERATIONS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
        out = dispatch(name, args)
        text = json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {"content": [{"type": "text", "text": text}], "isError": not out.get("ok", False)},
        }
    if method is not None and method.startswith("notifications/"):
        return None
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main(stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    src = stdin if stdin is not None else sys.stdin
    dst = stdout if stdout is not None else sys.stdout
    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:  # noqa: BLE001 — ignore unparseable frames, keep serving
            continue
        resp = handle(msg)
        if resp is not None:
            dst.write(json.dumps(resp) + "\n")
            dst.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
