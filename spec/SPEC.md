# Deterministic Calendar Engine — Specification v1.0.0

A deterministic, offline, host-independent calendar scheduling engine. Structured JSON in → structured
JSON out. Same input → **byte-identical** output on any machine. No ambient clock (you pass `now`), no
host time zone (time zones are explicit), no network, no state.

- Recurrence follows **RFC 5545** (iCalendar).
- Time zones come from a **pinned, vendored IANA release** (see each response's `meta.tzdata`), read
  through a fixed bundle — never the host.
- Intervals are **half-open `[start, end)`**: back-to-back events do not conflict.

## Operations

Nine operations. Each request/response is JSON. The request schema for each is published under
[`spec/schemas/<op>.schema.json`](./schemas) (JSON Schema draft 2020-12).

| Operation | Purpose |
|---|---|
| `resolve_timezone` | Instant ↔ wall-clock in a time zone; DST resolution. |
| `check_availability` | Free/busy over a window given events. |
| `detect_conflicts` | Pairwise overlaps among events (strict overlap). |
| `find_slots` | Open slots in candidate windows under constraints. |
| `create_event_plan` | A create **plan** (diff, not a live write) with an idempotency key. |
| `reschedule_event_plan` | A reschedule plan (`preserveElapsed` / `preserveWallClock`). |
| `cancel_event_plan` | A cancel plan (whole-event tombstone or single-occurrence EXDATE). |
| `expand_recurrence` | Materialize occurrences of an RFC 5545 series. |
| `next_occurrence` | The first occurrence strictly after an instant. |

Mutating operations return **plans/diffs only** — a provider adapter performs any live writes.

## Response envelope

Every response is one of:

```jsonc
{ "ok": true,  "result": { ... }, "meta": { ... } }
{ "ok": false, "error":  { "code": "...", "message": "...", "details": { ... }, "retryable": false }, "meta": { ... } }
```

`meta` is constant per build:

```jsonc
{ "schemaVersion": "0.1", "engine": "...", "engineVersion": "...", "policyVersion": "2026.1",
  "tzdata": "2025b", "icu": "none" }
```

- `engineVersion` is **implementation-specific** (the package version) and is the only field a
  conforming implementation may vary; conformance ignores it.
- `policyVersion` echoes the resolved policy profile's version for operations that resolve one
  (`find_slots`, the three `*_event_plan` ops); otherwise the engine default `2026.1`.
- `icu: "none"` denotes the engine never consults host ICU/`Intl`.

## Core types

```
Instant   = { "epochMs": <integer, UTC milliseconds> }
WallTime  = { "year","month","day","hour","minute","second" }   // all integers
Interval  = { "start": Instant, "end": Instant }                 // half-open [start, end)
DstPolicy = { "gap": "earliest"|"latest"|"reject", "overlap": "earliest"|"latest"|"reject" }
```

`DstPolicy` is **required** wherever a wall-clock time is resolved to an instant (any `wall` input and
the plan operations): `gap` resolves a nonexistent spring-forward time, `overlap` an ambiguous
fall-back time.

## Canonical JSON (determinism)

Output is canonical so it is byte-identical across implementations:

1. Object keys sorted lexicographically by code unit (recursively).
2. Arrays keep producer order.
3. Numbers are integers where applicable; `-0` normalizes to `0`; non-finite numbers are rejected.
4. `undefined`/absent values are omitted from objects.
5. No insignificant whitespace. A trailing newline is added by the CLI only (not by the value itself).

`idempotencyKey` and `planId` are `sha256(canonicalJson(...))` of resolved content, so two requests
that resolve to the same plan share a key regardless of serialization or omitted defaults; `inputHash`
fingerprints the request.

## Error model

Errors are structured (never a stack trace). `retryable` is always `false` (the engine is
deterministic; there are no transient failures). Codes:

`SCHEMA_VALIDATION_ERROR`, `INVALID_INTERVAL`, `INVALID_TIME_ZONE`, `MISSING_TIME_ZONE`,
`MISSING_DST_POLICY`, `NONEXISTENT_WALL_TIME`, `AMBIGUOUS_WALL_TIME`, `UNBOUNDED_RECURRENCE`,
`RECURRENCE_LIMIT_EXCEEDED`, `NO_VALID_SLOT`, `CONFLICT_FOUND`, `STALE_OVERRIDE`, `INPUT_TOO_LARGE`,
`MAX_EVENTS_EXCEEDED`, `MAX_CALENDARS_EXCEEDED`, `MAX_WINDOW_EXCEEDED`; plus the dispatch codes
`UNKNOWN_OPERATION` and `OPERATION_NOT_IMPLEMENTED`.

CLI exit codes: `0` success, `1` operation error (`ok:false`), `2` CLI/input error (bad args or
unparseable input).

## Conformance

[`conformance/vectors/<op>/*.json`](../conformance/vectors) are golden `{ input, expected }` fixtures.
Any implementation must reproduce every `expected` (the full envelope except `meta.engineVersion`).
Run them with [`conformance/run.py`](../conformance/run.py) against your build. Vectors are the binding
definition of correct behavior; they are versioned with this spec.

## Versioning

This spec is semver'd. Behavioral changes that alter conformance vectors are a **major** bump. The
`tzdata` release is pinned per build and reported in `meta.tzdata`; updating it is a versioned change
with regenerated vectors.
