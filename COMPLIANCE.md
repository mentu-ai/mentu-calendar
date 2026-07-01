# Compliance & Data Posture

`mentu-calendar` is designed and tested to be fully offline and side-effect-free. Inputs are processed
in-process and returned; nothing is stored, logged, or transmitted.

| Property | Guarantee | Evidence |
|---|---|---|
| **No network** | The engine opens no sockets and makes no network calls. | `tests/test_properties.py::test_no_network` runs a spread of operations with `socket.socket` and `socket.create_connection` monkeypatched to raise. |
| **No ambient clock** | `now` is an explicit input; the engine never reads the system clock. | No `datetime.now()` / `time.time()` in `src/`; determinism below. |
| **No host time zone** | Zones resolve from the pinned `tzdata` wheel, read per-zone, never the host tz database. | `src/mentu_calendar/tz.py`. |
| **Deterministic** | Same input → byte-identical output. | `tests/test_properties.py::test_byte_identical_repeat`; the conformance vectors. |
| **Host-state independent** | Output never depends on mutable process/host state — `calendar.firstweekday()` (RFC 5545 WKST is pinned), the `TZ` environment variable, or the active locale. | `tests/test_hardening.py::test_wkst_independent_of_host_firstweekday`. |
| **Bounded resources** | Recurrence expansion is bounded — a terminating bound is required, occurrences are capped, and a never-satisfiable rule terminates (never scans to the year-9999 ceiling). | `tests/test_hardening.py` (`*_occurrence_cap_is_bounded`, `*_returns_empty_and_is_bounded`, `*_unbounded_recurrence_rejected`). |
| **No secrets / no state** | No credentials read, no files written, no state retained across calls. | Pure functions; no filesystem writes. |
| **No PII persistence** | Nothing is stored or transmitted; data lives only for the duration of the call. | By construction. |
| **Pinned tz data** | The IANA release is pinned and reported in every response's `meta.tzdata`. | `tzdata==2025.2` → IANA `2025b`, asserted at load. |

This posture supports data-protection regimes (e.g. GDPR, Mexico's LFPDPPP) where input data must not
leave the process boundary.

## Verify it yourself

```bash
pip install mentu-calendar
python -m pytest tests/test_properties.py -k "no_network or byte_identical"   # offline + determinism
python conformance/run.py                                                      # full behavioral lock
```

Or run the CLI under an OS network sandbox (e.g. `sandbox-exec` on macOS, `firejail`/`unshare -n` on
Linux) — every operation completes with the network denied.
