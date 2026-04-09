# AGENTS.md

## Setup
- Match CI when preparing an environment: `python -m pip install --upgrade pip`, then `pip install -r requirements.txt`, then `pip install -e .`.
- Do not assume the ambient `python` has deps installed. In this repo, `python -m unittest discover tests` fails without `requests`; use the checked-in `.venv` or install first.
- CI runs on Python 3.11 (`.github/workflows/python-tests.yml`). Package metadata allows `>=3.7` (`setup.py`).

## Repo Shape
- Single-package repo. Production code is under `PyFetch/`; tests are under `tests/`.
- Console entrypoint is `pyfetch=PyFetch.cli:main` in `setup.py`.
- Module execution path is `python -m PyFetch` via `PyFetch/__main__.py`.
- Main wiring:
  - `PyFetch/cli.py`: argparse subcommands, JSON/header parsing, CLI output.
  - `PyFetch/http_client.py`: request execution, retries, verbose logging, download progress handling.
  - `PyFetch/exceptions.py`: custom exception types.

## Verification
- Canonical test command: `python -m unittest discover tests`.
- Focused runs: `python -m unittest tests.test_cli`, `python -m unittest tests.test_http_client`, `python -m unittest tests.test_exceptions`.
- On Windows in this workspace, `.venv\Scripts\python.exe -m unittest discover tests` works without extra setup.
- Tests are unit tests with mocks; they do not require external services.
- `tests/test_http_client.py` triggers real `tqdm` output in the suite for progress-path coverage; that noisy output is expected.

## Repo-Specific Quirks
- Import/package name is `PyFetch` (capitalized). Installed CLI command is lowercase `pyfetch`.
- CLI subcommands are case-insensitive because `cli.main()` normalizes `args.command.upper()`.
- `--progress` is only supported for `GET`; `tests/test_cli.py` checks that `POST ... --progress` exits.
- `HTTPClient.make_request()` unconditionally sets `stream=True` for `GET` requests so progress/download handling works. Preserve that behavior when changing GET request flow.

## What Not To Invent
- There is no repo-local lint, formatter, type-check, tox, pre-commit, Makefile, or task-runner config checked in. Do not document or claim commands for them unless you add the config in the same change.
