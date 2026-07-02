# mentu-calendar

[![CI](https://github.com/mentu-ai/mentu-calendar/actions/workflows/ci.yml/badge.svg)](https://github.com/mentu-ai/mentu-calendar/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mentu-calendar.svg)](https://pypi.org/project/mentu-calendar/)
[![Python](https://img.shields.io/pypi/pyversions/mentu-calendar.svg)](https://pypi.org/project/mentu-calendar/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)

Deterministic, offline, host-independent calendar scheduling for agents and services. Structured JSON
in → structured JSON out, with **byte-identical** output on any machine.

A clean-room implementation of **RFC 5545** (recurrence), **RFC 8536** (TZif), and the **IANA tzdata**
database — no ambient clock (you pass `now`), no host time zone (time zones are explicit), no network,
no state.

## Why

- **Deterministic** — the same input JSON produces byte-identical output JSON. Reproducible in your
  own CI against the published conformance vectors.
- **Offline & host-independent** — no network, no host clock, no host time-zone database. Zones come
  from a pinned IANA release (the `tzdata` wheel), read per-zone.
- **Half-open `[start, end)` intervals** — back-to-back events do not conflict.
- **Auditable & vendorable** — pure Python, Apache-2.0, zero closed binaries; installs clean and
  passes standard dependency scanning (`pip-audit`, SBOM).

## Install

```bash
pip install mentu-calendar
```

Requires Python ≥ 3.12. Dependencies: `python-dateutil` and the pinned `tzdata` wheel.

## Library

```python
from mentu_calendar import dispatch

out = dispatch("resolve_timezone", {"zoneId": "America/Mexico_City", "instant": {"epochMs": 1736942400000}})
# {"ok": True, "result": {...}, "meta": {...}}
```

## CLI

```bash
mentu-calendar call find_slots --input request.json   # or pipe JSON on stdin
mentu-calendar --schema [op]                          # JSON request schema(s)
mentu-calendar --self-test
mentu-calendar --version
```

Exit codes: `0` success, `1` operation error, `2` CLI/input error.

## Operations

`resolve_timezone`, `check_availability`, `detect_conflicts`, `find_slots`, `create_event_plan`,
`reschedule_event_plan`, `cancel_event_plan`, `expand_recurrence`, `next_occurrence`.

Mutating operations return **plans/diffs only** — a provider adapter performs any live writes.

## MCP server

A dependency-free stdio [MCP](https://modelcontextprotocol.io) server exposes all nine operations as
tools for agent runtimes (Claude Desktop, IDE agents, …):

```bash
mentu-calendar-mcp        # JSON-RPC 2.0 over stdio; each operation is a tool
```

Example Claude Desktop config:

```json
{ "mcpServers": { "calendar": { "command": "mentu-calendar-mcp" } } }
```

## Contract & conformance

The full specification is [`spec/SPEC.md`](./spec/SPEC.md); the versioned request schemas are in
[`spec/schemas/`](./spec/schemas) (JSON Schema draft 2020-12). Golden `{ input, expected }` fixtures
under [`conformance/vectors/`](./conformance/vectors) are the binding definition of correct behavior —
run them against your build:

```bash
python conformance/run.py            # against the installed package
```

Correctness is additionally locked by property tests (determinism, offline, host-state independence)
and by [`tests/test_reference_crosscheck.py`](./tests/test_reference_crosscheck.py), which recomputes
the expected answers independently — timezone resolution with the standard-library `zoneinfo`,
recurrence with a plain `dateutil.rrule` — over thousands of seeded inputs. Every claim in this README
is reproducible with `pytest` + `python conformance/run.py`.

## Adopting this as a dependency

Evaluating it for a team (including regulated environments)? [`docs/ADOPTING.md`](./docs/ADOPTING.md)
maps every claim to the command that proves it — verify it yourself, offline, in ~10 minutes; it also
covers provenance, supply chain (SBOM + SLSA attestation), versioning/stability, and vendoring.

## Guarantees

Fully offline, no telemetry, no ambient clock, no secrets, nothing leaves the process — see
[`COMPLIANCE.md`](./COMPLIANCE.md). Security policy: [`SECURITY.md`](./SECURITY.md).

## Provenance

A clean-room implementation of public standards — **RFC 5545**, **RFC 8536**, and the **IANA tzdata**
database — built on the Python standard library (`zoneinfo`), `python-dateutil` (an independent RFC
5545 implementation), and the `tzdata` wheel. No proprietary code.

## License

Apache-2.0 — see [`LICENSE`](./LICENSE) and [`NOTICE`](./NOTICE).
