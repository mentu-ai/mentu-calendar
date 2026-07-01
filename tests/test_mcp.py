"""MCP stdio server: handshake, tool listing, tool calls, and a full stdio round-trip."""

from __future__ import annotations

import io
import json

from mentu_calendar import OPERATIONS
from mentu_calendar.mcp import PROTOCOL_VERSION, handle, main


def test_initialize() -> None:
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r is not None
    assert r["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert r["result"]["serverInfo"]["name"] == "mentu-calendar"
    assert "tools" in r["result"]["capabilities"]


def test_tools_list_exposes_every_operation() -> None:
    r = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert r is not None
    tools = r["result"]["tools"]
    assert {t["name"] for t in tools} == set(OPERATIONS)
    for t in tools:
        assert t["inputSchema"]["type"] == "object"
        assert t["description"]


def test_tools_call_success() -> None:
    r = handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "resolve_timezone",
                "arguments": {"zoneId": "Asia/Tokyo", "instant": {"epochMs": 1736942400000}},
            },
        }
    )
    assert r is not None and r["result"]["isError"] is False
    out = json.loads(r["result"]["content"][0]["text"])
    assert out["ok"] is True and out["result"]["offsetSeconds"] == 32400


def test_tools_call_operation_error_maps_to_iserror() -> None:
    r = handle(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "resolve_timezone", "arguments": {}}}
    )
    assert r is not None and r["result"]["isError"] is True
    assert json.loads(r["result"]["content"][0]["text"])["ok"] is False


def test_unknown_tool_is_jsonrpc_error() -> None:
    r = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
    assert r is not None and "error" in r


def test_notifications_get_no_response() -> None:
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_full_stdio_roundtrip() -> None:
    reqs = (
        "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "detect_conflicts", "arguments": {"events": []}},
                    }
                ),
            ]
        )
        + "\n"
    )
    out = io.StringIO()
    main(stdin=io.StringIO(reqs), stdout=out)
    lines = [json.loads(x) for x in out.getvalue().splitlines() if x.strip()]
    assert [x["id"] for x in lines] == [1, 2]  # notification produced no response
