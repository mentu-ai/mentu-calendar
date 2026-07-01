# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to semantic versioning.

## [0.1.0]

Initial release.

- Deterministic, offline, host-independent calendar engine with nine operations: `resolve_timezone`,
  `check_availability`, `detect_conflicts`, `find_slots`, `create_event_plan`,
  `reschedule_event_plan`, `cancel_event_plan`, `expand_recurrence`, `next_occurrence`.
- RFC 5545 recurrence, RFC 8536 TZif, pinned IANA tzdata `2025b`, half-open `[start, end)` intervals,
  structured errors, byte-identical canonical output.
- Published specification (`spec/`) and conformance vectors (`conformance/`) — the binding contract.
- Three interfaces: library (`from mentu_calendar import dispatch`), CLI (`mentu-calendar`), and a
  dependency-free stdio MCP server (`mentu-calendar-mcp`).
- Correctness validated by the conformance vectors plus property tests (determinism, offline,
  host-state independence) and differential testing against an independent implementation over
  thousands of randomized inputs; recurrence expansion is resource-bounded.
