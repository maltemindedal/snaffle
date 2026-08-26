# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- The `-d`/`--data` help text no longer prints a literal `R|` prefix:
  `-d, --data DATA  R|JSON data for request body.` The marker belonged to a
  custom help formatter that was only ever attached to the top-level parser,
  never to the subcommands carrying the marker, so it leaked into the output it
  was meant to control. Both the formatter and the marker are gone.
- Corrected the documented exception mapping, which was wrong in two places.
  Retries exhausted against a server that kept returning a transient status
  raise `ResponseError` carrying the real status, not `HTTPConnectionError` —
  the adapter is built with `raise_on_status=False`, so the last response is
  reported rather than discarded. And a connect timeout raises
  `HTTPConnectionError`, not `HTTPClientError`, because
  `requests.exceptions.ConnectTimeout` subclasses `ConnectionError`. Only read
  timeouts reach `HTTPClientError`. Behaviour is unchanged; the documentation
  now matches it.
- `HTTPClient.allowed_methods` is now the attribute method validation actually
  reads. It was assigned in `__init__` and documented, but every request
  checked the `ALLOWED_METHODS` class constant instead, so the instance
  attribute did nothing.
- `stream=True` is no longer ignored when `show_progress` is on. A `GET` the
  caller asked to stream now comes back unread, as the API reference, the
  architecture overview and ADR 0001 all already claimed; previously the
  progress bar drained the body anyway and the caller got nothing to iterate.
  A caller who wants both a stream and a bar drives `tqdm` themselves, which is
  what the large-download guide has always said.
- The exit-code table in the CLI reference omitted a path: an argument value the
  client rejects, such as `-t 0`, exits `1` through a `ValueError` from
  `HTTPClient.__init__`. It is now listed, along with a non-integer `-t` under
  code `2`. Behaviour is unchanged; the documentation now matches it.

### Changed

- Relicensed from Apache-2.0 to MIT. The `license` field in `pyproject.toml`
  and the `LICENSE` file both carry the new terms; releases up to and including
  3.0.0 remain available under Apache-2.0.
- `snaffle.__version__` is read from the installed distribution's metadata
  instead of being hard-coded, so the version is declared once, in
  `pyproject.toml`. It resolves lazily through the same PEP 562 hook as
  `HTTPClient`, so `import snaffle` does not pay for the lookup. The value is
  unchanged.
- The CLI dispatches through `HTTPClient.make_request(method, url)` rather than
  looking the per-verb method up by name with `getattr`.
- The progress-bar download moved into a private `snaffle._download` module,
  which owns the decision to drain, the size threshold, the deferred `tqdm`
  import, the chunk loop, and the write-back onto the response.
  `DOWNLOAD_CHUNK_SIZE` and `MIN_SIZE_FOR_PROGRESS` remain public attributes of
  `HTTPClient`, and `ProgressBar` is still importable from
  `snaffle.http_client`. The private `HTTPClient._stream_response` and
  `HTTPClient._create_progress_bar` are gone.
- `snaffle.cli.main` returns an exit code instead of calling `sys.exit`, and
  `snaffle.__main__.run` is now the single process-level exit point, so the
  error-to-code mapping is one visible thing in one module. `argparse` still
  exits `2` from inside `parse_args`; that is a distinct mechanism and is
  documented rather than routed through the return value. Observable behaviour
  is unchanged — same messages, same codes, same stdout — but code that
  embedded `cli.main` and caught `SystemExit` to detect an error must check the
  return value instead.
- The seven verb methods (`get`, `post`, `put`, `patch`, `delete`, `head`,
  `options`) carry a one-line docstring pointing at `make_request` rather than
  restating its arguments and return value seven times over. Signatures and
  behaviour are unchanged; `help()` output is shorter.

### Added

- ty as the project's type checker, with every rule at error level
  (`[tool.ty.rules] all = "error"`). It replaces mypy, whose `strict = true`
  configuration was the equivalent bar. Satisfying it added `@override`
  decorators (via `typing_extensions`, since the project floor is 3.10) to the
  test doubles in `tests/test_http_client.py` and corrected two of their
  signatures — `log_message` and `handle_error` collapsed their base class's
  parameters into `*args`, which violated the base signatures they claimed to
  override.
- A `docs/` tree covering the tutorial, how-to guides, CLI and Python API
  reference, and the architecture, including decision records for the retry
  policy, the lazy imports, and the src-layout move. `README.md` is now a front
  door that links into it.
- Test modules for `__init__.py` and `__main__.py`, the two source modules that
  had none. These cover the `Ctrl+C`-exits-`0` contract of the console script,
  the lazy resolution of `HTTPClient` and `__version__`, and a subprocess guard
  that `import snaffle` does not pull in `requests`.
- `HTTPClient` accepts a `session`, so the transport can be substituted at the
  client's own interface instead of by patching `requests.Session.request`.
  That patch point sits below the client and above the adapter, which is where
  urllib3 retries, so it can never observe a retry — the project shipped a false
  claim about `POST` retry behaviour on exactly that mistake. A session mounted
  with a test adapter now observes retries with no socket opened. The parameter
  is last and defaults to `None`, which builds the pooled, retrying session as
  before; a session passed in is used as it arrives, so `retries` does not apply
  to it, and the client closes only a session it built. See ADR 0004.
- ADR 0004, recording the session seam. It supersedes only the mitigation in
  ADR 0001's Consequences — documenting the mock trap — and not its decision.

### Removed

- mypy, in favour of ty (see Added). The `[tool.mypy]` configuration is gone
  from `pyproject.toml`, including the `build/`/`dist/` excludes it needed —
  ty honours `.gitignore`, so build output is skipped without configuration.
  `types-requests` stays: ty reads the same stubs for `requests`.
- `snaffle.cli.show_examples` and the `suppress_output` parameter of
  `snaffle.cli.main`. Neither was part of the documented public API — that is
  `HTTPClient` and the three exceptions — and the flag existed only to quiet
  tests that already redirect stdout.

## [3.0.0] - 2026-07-23

### Changed

- **BREAKING**: the project is named Snaffle. The import package, the
  distribution, and the console script are all `snaffle`:

  ```python
  from snaffle import HTTPClient
  ```

  ```bash
  snaffle GET https://example.com
  ```

## [2.0.0] - 2026-07-23

### Changed

- **BREAKING**: the import package is all-lowercase, per PEP 8 ("Python
  packages should also have short, all-lowercase names").
- Moved the package under `src/`, following the PyPA src-layout recommendation.
  Tests now exercise the installed package rather than the working directory.
- The console script points at `__main__:run` instead of `cli:main`, so it
  handles `Ctrl+C` the same way `python -m` always did. Previously the console
  script exited with a traceback.
- `argparse` usage output is pinned to the command name rather than deriving
  from `sys.argv[0]`.

### Added

- A PEP 561 `py.typed` marker. The package had been `mypy --strict` clean for
  some time, but without this marker downstream type checkers ignored all of
  its annotations.
- `CONTRIBUTING.md`, `CHANGELOG.md`, and `.editorconfig`.

## [1.1.0] - 2026-07-23

### Changed

- The client keeps a pooled `requests.Session` for its lifetime, so repeat
  requests to a host reuse the TCP/TLS connection. A repeat HTTPS request went
  from 24.5 ms to 6.2 ms; 200 requests now open 1 connection instead of 200.
- Retries moved to a urllib3 `Retry` on the session adapter, with exponential
  backoff and `Retry-After` support. Only connection failures and transient
  statuses (408, 425, 429, 500, 502, 503, 504) are retried; a `404` now costs
  one round trip instead of three. Read failures and retryable statuses are not
  retried for `POST`/`PATCH`; connection failures are retried for every method,
  because a request that never reached the server cannot have been acted on
  twice.
- `GET` no longer forces `stream=True` unless `--progress` is passed.
- `HTTPClient` now owns a connection and should be closed; it supports the
  context manager protocol and a `close()` method.
- `DOWNLOAD_CHUNK_SIZE` raised from 8 KiB to 64 KiB.
- CLI start-up fell from 238 ms to 80 ms: `HTTPClient` resolves lazily via
  PEP 562 and `tqdm` is imported only when a progress bar is drawn, so the help
  paths no longer import `requests`.

### Added

- Optional `speedups` extra (`zstandard`, `brotli`) enabling Zstandard and
  Brotli transfer compression.
- Support declared and tested for Python 3.12, 3.13, and 3.14.

## [1.0.0]

- Initial release.

[3.0.0]: https://github.com/maltemindedal/snaffle/releases/tag/v3.0.0
[2.0.0]: https://github.com/maltemindedal/snaffle/releases/tag/v2.0.0
[1.1.0]: https://github.com/maltemindedal/snaffle/releases/tag/v1.1.0
[1.0.0]: https://github.com/maltemindedal/snaffle/releases/tag/v1.0.0
