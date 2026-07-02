# Adopting `mentu-calendar` (auditing it as a dependency)

This is the maintainer's honest guide for teams — including regulated shops — evaluating whether to
take `mentu-calendar` as a dependency. It is **not** a neutral third-party audit; it is written by the
author. So it is built around one principle: **don't trust anything here — reproduce it.** Every claim
below names the command that proves it, and all of them run **offline** against the pinned data.

## TL;DR for an evaluator

```bash
git clone https://github.com/mentu-ai/mentu-calendar && cd mentu-calendar
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

python conformance/run.py    # 151/151 golden {input,expected} vectors — the behavioral contract
pytest -q                    # full suite incl. reference cross-checks, determinism, offline
pip-audit                    # dependency CVE scan
mentu-calendar --self-test   # PASS (deterministic=true, tzdata=2025b)
```

If those pass on your machine, the claims in this repo are true **for you** — not because we said so.

## Claim → how you verify it

| Claim | Reproduce it |
| --- | --- |
| **Correct** (matches the reference libraries) | `pytest tests/test_reference_crosscheck.py` — recomputes timezone resolution with the stdlib `zoneinfo` and recurrence with a plain `dateutil.rrule`, independently, and asserts the engine agrees over thousands of seeded inputs. |
| **Contract is frozen + reproducible** | `python conformance/run.py` — 151 golden `{input, expected}` fixtures in `conformance/vectors/`; the engine must reproduce each byte-for-byte (except `meta.engineVersion`). |
| **Deterministic** | `pytest tests/test_properties.py -k byte_identical` — same input → byte-identical output. |
| **Offline / no network** | `pytest -k no_network` (blocks sockets), or run under an OS network sandbox: `sandbox-exec -p '(version 1)(allow default)(deny network*)' mentu-calendar --self-test`. |
| **Host-state independent** | `pytest tests/test_hardening.py -k firstweekday` — output does not depend on `calendar.firstweekday()`, `TZ`, or the locale. |
| **Bounded (no runaway recurrence)** | `pytest tests/test_hardening.py -k "cap or bounded or unbounded"`. |
| **No known CVEs / small dep tree** | `pip-audit`; deps are only `python-dateutil` + the pinned `tzdata` wheel (see `pyproject.toml`). |
| **Supply chain** | CI publishes a **CycloneDX SBOM** and a **SLSA build-provenance attestation** — see the latest run of `.github/workflows/ci.yml` (Actions tab) and `gh attestation verify` on released artifacts. |

## Provenance (and how to check it)

`mentu-calendar` is a **clean-room implementation of public standards** — RFC 5545 (iCalendar
recurrence), RFC 8536 (TZif) and the IANA time-zone database — built on the Python standard library
(`zoneinfo`), `python-dateutil` (an independent RFC 5545 implementation) and the `tzdata` wheel. There
is no proprietary code; the license is Apache-2.0.

You do not have to take that on faith:

1. **Dependencies** are exactly those two public libraries — `pyproject.toml`.
2. **Behavior is specified against the standards** — `spec/SPEC.md` + `spec/schemas/`.
3. **Behavior is checked against those reference libraries** — `tests/test_reference_crosscheck.py`
   compares the engine directly to `zoneinfo` and `dateutil`.
4. **The date math is auditable** — the civil-date conversion is a small, self-contained algorithm in
   `src/mentu_calendar/temporal.py`; the cross-check test validates it against `datetime`/`zoneinfo`.

## Data posture

Fully offline, no telemetry, no ambient clock (`now` is an explicit input), no host time zone (zones
come from the pinned `tzdata` wheel), no secrets, no state retained across calls. Details + evidence in
[`COMPLIANCE.md`](../COMPLIANCE.md); security policy in [`SECURITY.md`](../SECURITY.md).

## Versioning & stability

- **Semantic versioning.** The **contract** is `spec/` + `conformance/vectors/`; a behavior change that
  would alter a vector is a breaking change and bumps the major once ≥ 1.0. Pre-1.0 (`0.x`), treat
  minor bumps as potentially breaking and pin exactly.
- Every response carries `meta` (`schemaVersion`, `engine`, `engineVersion`, `policyVersion`, `tzdata`,
  `icu`) so you can assert what produced a result.
- **Reproducibility across hosts** depends on the tz release: `tzdata` is pinned (`2025.2` → IANA
  `2025b`) and echoed in `meta.tzdata`. A tz bump is a deliberate, versioned change.

## Vendoring / mirroring (for closed networks)

Pure Python, no compiled or closed components. Pin exactly and mirror to a private index:

```
mentu-calendar==0.1.0
python-dateutil>=2.9
tzdata==2025.2
```

`pip download mentu-calendar==0.1.0` fetches the pure `py3-none-any` wheel + its deps for an offline /
air-gapped install, or vendor the `src/mentu_calendar/` package directly into a monorepo.

## What it does **not** do

- **Plans, not writes.** `create/reschedule/cancel_event_plan` return a diff + `idempotencyKey`;
  persisting a booking is your provider adapter's job. It is not a calendar store or CRM.
- **It is not a data source.** You pass the busy `events` and candidate windows; it does the interval
  math, not the fetching.
- **It is not a clock.** You pass `now` — that is what makes it deterministic.

## License & support

Apache-2.0 ([`LICENSE`](../LICENSE), [`NOTICE`](../NOTICE)). Issues and security reports:
[`SECURITY.md`](../SECURITY.md) and the GitHub issue tracker.
