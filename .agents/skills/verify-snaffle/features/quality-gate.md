# Pre-PR gate and wheel

## Sub-features

- `ruff check`, `ruff format --check` (Markdown included), `ty check`, `unittest` under `-X dev -W error`, `uv build`, and the wheel's `snaffle/py.typed`.

## How to get to it (user POV)

A contributor runs the gate in `AGENTS.md`; CI runs it on Python 3.10 to 3.14.

## Driving it with verify.sh

`verify.sh test`. Every step must exit 0, unittest must print `OK` with no
`ResourceWarning`, and the wheel must list `snaffle/py.typed`.

## Gotchas

- Only the `.venv` interpreter runs locally; CI covers the other Python versions.
