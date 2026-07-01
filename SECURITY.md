# Security Policy

## Reporting a vulnerability

Please report suspected security issues privately to **rashid.azarang.eg@gmail.com**. Include a
description, reproduction steps, and the affected version. We aim to acknowledge within 5 business
days and to publish a fix and advisory promptly.

Please do not open public issues for security reports.

## Supported versions

Security fixes are released for the latest `0.x` minor. CVEs are published against the
`mentu-calendar` PyPI package.

## Posture

`mentu-calendar` performs **no network I/O**, reads **no secrets**, and retains **no state** across
calls (see [`COMPLIANCE.md`](./COMPLIANCE.md)). The primary attack surface is untrusted JSON input,
which is validated and returned as structured errors — malformed input never crashes the process or
escapes as an exception. Recurrence expansion is **resource-bounded**: it requires a terminating
bound, caps the number of materialized occurrences, and terminates on never-satisfiable rules rather
than scanning an unbounded date range. Time-zone data is a pinned dependency (`tzdata`), scannable via
SBOM and `pip-audit`.
