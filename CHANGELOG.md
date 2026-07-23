# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
