# Contributing to Snaffle

Documentation lives in [`docs/`](docs/README.md); the
[architecture overview](docs/architecture/overview.md) and the
[decision records](docs/architecture/decisions/) explain why the code is shaped
the way it is.

## Project layout

```
src/snaffle/        The package. src-layout, so tests run against the
                    installed distribution rather than the working directory.
  __init__.py       Public API. Resolves HTTPClient and __version__ lazily
                    (PEP 562).
  __main__.py       `python -m snaffle` and the `snaffle` console script.
  cli.py            Argument parsing and response rendering.
  http_client.py    The HTTP client, session pooling, and retry policy.
  exceptions.py     Exception hierarchy.
  py.typed          PEP 561 marker.
tests/              One test module per source module: test_<module>.py.
                    Dunder modules drop the underscores, so `__init__.py` is
                    covered by `test_init.py` and `__main__.py` by
                    `test_main.py`.
```

Conventions:

- Package and module names are short and all-lowercase (PEP 8). The import
  package is `snaffle`; there is no `Snaffle`.
- Every public module, class, and function carries a docstring — including
  dunder methods such as `__enter__` and `__exit__`.
- The version is declared once, in `pyproject.toml`. `snaffle.__version__`
  reads it back from the installed distribution's metadata; do not hard-code
  it in a second place.
- Imports of first-party code are absolute (`from snaffle.exceptions import ...`),
  never relative.
- Anything that would import `requests` at module scope should be deferred, so
  that the CLI's help paths stay fast. `tests/test_cli.py` guards this.

## Getting set up

```bash
uv sync --group dev --extra speedups
```

## Before opening a pull request

All four must pass; CI runs them on Python 3.10 through 3.14.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run python -m unittest discover tests
```

To apply formatting: `uv run ruff format .`

## Testing notes

Type checking runs in `mypy --strict` over both `src/` and `tests/`.

Do not mock `requests.Session.request` when the behaviour under test involves
retries. That mock sits *above* the adapter where urllib3's retry logic lives,
so it cannot observe retries at all — an earlier revision shipped a false claim
about `POST` retry behaviour on exactly that mistake. Use
`TestRetryAgainstRealServer`, which counts requests arriving at a real socket,
or assert against `urllib3.util.retry.Retry` directly.

## Changelog

User-visible changes go in `CHANGELOG.md` under an `Unreleased` heading,
following Keep a Changelog. The project follows semantic versioning; the import
package name is part of the public API, so renaming it is a major bump.
