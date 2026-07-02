# Contributing

Thanks for your interest in `mentu-calendar`. It is a small, deterministic, dependency-light engine —
contributions are welcome as long as they keep it that way.

## Development setup

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Definition of done (what CI enforces)

Every change must pass, locally and in CI:

```bash
ruff format .            # formatting
ruff check .             # lint
mypy                     # types
pytest -q                # unit + property + cross-check tests
python conformance/run.py  # the 151 golden vectors
pip-audit                # dependency CVE scan
```

## The contract is the spec + the vectors

`spec/` (the specification + JSON Schemas) and `conformance/vectors/` (the golden `{input, expected}`
fixtures) define correct behavior.

- A bug fix that changes output **must** update the affected vectors in the same PR, with an
  explanation of why the old output was wrong. Do not regenerate vectors to make a red test green.
- New behavior ships with new vectors **and** unit/property tests.
- `tests/test_reference_crosscheck.py` cross-checks against `zoneinfo`/`dateutil`; keep it green.

## Principles to preserve

- **Deterministic**: no ambient clock (`now` is always an input), no host time zone, no network, no
  hidden state. Byte-identical output for a given input.
- **Dependency-light**: only `python-dateutil` + the pinned `tzdata` wheel. Adding a runtime dependency
  needs a strong justification.
- **Structured errors**: never let an exception escape `dispatch`; return `{ok:false, error:{...}}`.

## Pull requests

Keep PRs focused. Describe what changed and how you verified it. By contributing you agree your work is
licensed under the project's Apache-2.0 license.
