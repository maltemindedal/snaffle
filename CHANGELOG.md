# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- The `urllib3` floor is now 2.8.0, which fixes three advisories that a
  hostile server could reach through any response snaffle reads:
  `GHSA-vxq7-64xx-v4gw` (a chunk-size line of unbounded length was buffered in
  memory; one response pushed a client's memory use up by more than 500 MiB),
  `GHSA-gh4c-6fx4-qh6g` (chunked `deflate` streaming could loop forever) and
  `GHSA-8988-9cw3-xx77` (the TLS settings for an HTTPS proxy could be ignored).
  A response with an oversized chunk-size line now fails as
  `HTTPClientError`. urllib3 2.8.0 also rejects hosts containing a raw space or
  a control character while parsing the URL, so `http://exa mple.com/` now
  raises `HTTPClientError` ("Request failed: ...") instead of
  `HTTPConnectionError` after a failed DNS lookup. The exit code of the CLI is
  `1` either way.
- The `tqdm` floor is now 4.66.3. 4.66.0 to 4.66.2 are affected by
  `GHSA-g7vv-2v7x-gj9p` (`CVE-2024-34062`, low severity, argument injection in
  the `python -m tqdm` command line). snaffle only calls the `tqdm()` API, so it
  was not reachable, but a floor should not admit a version with a published
  advisory.

### Fixed

- The large-download guide claimed that letting `requests` read a `GET` body in
  one pass is faster than draining it. It is not, for bodies of about 100 KiB
  and up: `requests` reads in 10 KiB chunks where the progress path reads
  `DOWNLOAD_CHUNK_SIZE` (64 KiB), and against a local server the plain read
  measured 13% slower at 100 KiB, 56% at 1 MiB and 64% at 10 MiB. The default
  is unchanged; the guide now gives the reason that does hold, which is that no
  response is left streaming with nothing reading it.
- The progress bar no longer runs past 100% for a compressed download. Its total
  is the `Content-Length`, which counts the bytes the server sent, but it was
  advanced by the length of each decoded chunk, so a gzip, deflate, Brotli or
  Zstandard response of 5 MiB or more finished at several hundred percent and
  tqdm dropped the total. It now advances by the bytes read off the wire
  (`response.raw.tell()`), and falls back to the decoded length whenever that
  position is missing or does not behave like a byte count: a chunked body, a
  response from a caching session, or a test double. The recipe for driving your own bar in the
  large-download guide had the same flaw and is corrected. The bar is on stderr;
  stdout is unchanged.
- Piping the CLI into a reader that exits early, as in `snaffle GET URL | head -1`,
  no longer prints a `BrokenPipeError` traceback. A large body raised one
  (exit status `1`); a small body, still buffered when the CLI finished, failed
  during interpreter shutdown with `Exception ignored ... BrokenPipeError` and
  exit status `120`. Both now exit `1` with nothing on stderr, following the
  recipe in the `signal` module documentation. Scripts that tested for `120`
  must test for `1`.
- A JSON response nested too deeply for the parser no longer kills the CLI with
  a `RecursionError` traceback. The nesting exhausts Python's recursion limit,
  which is not a `ValueError`, so the plain-text fallback never ran and nothing
  was printed, not even the status or headers. The body is now printed as text,
  like any other body that is not valid JSON. A server chooses the body, so this
  was remotely triggerable.
- A response whose `Content-Length` is not an integer, such as `abc` or a
  duplicated header that urllib3 joins into `5, 5`, no longer makes a download
  with `show_progress` fail. The progress path called `int()` on the header and
  raised a bare `ValueError` before reading the body, although the same response
  reads fine without `show_progress`. An unparsable length now reads as `0`, the
  same as a missing one: the body is drained and no bar is drawn.
- A host that urllib3 cannot encode, such as `http://a..b/` (an empty label) or
  one with a label over 63 characters, no longer escapes `make_request` as a raw
  `urllib3.exceptions.LocationParseError`. It raises `HTTPClientError`, as the
  API reference already said a malformed URL does. The same held for a server
  that redirects to such a host. The CLI still exits `1`; its message gains the
  usual prefix, `Error: Request failed: Failed to parse: ...`. Code that caught
  `ValueError` around a call to catch this case must catch `HTTPClientError`.
- A `GET` with `show_progress` on that came back as a 4xx or 5xx no longer
  leaves its connection checked out. The request is sent as `stream=True`, and
  the error was raised without reading the body, so the socket stayed open until
  the exception was garbage collected. A script that kept its `ResponseError`
  objects held one socket per failure, and every failure lost connection reuse;
  `client.close()` could not release them. The error body is now read before
  the exception is raised, so `error.__cause__.response.text` still works. If
  that read fails, because the body is truncated, undecodable or stalls until the
  read timeout, the connection is closed and the `ResponseError` with the real
  status is still raised, as before. A large error body is now read in full. A
  caller who passes `stream=True` still gets the response unread.
- The `speedups` extra now installs the codecs urllib3 actually loads. It named
  `zstandard`, which urllib3 stopped using in 2.6.0, so on Python 3.10 to 3.13
  the documented Zstandard negotiation never happened even with the extra
  installed. The extra is now `brotli>=1.2.0` plus `backports-zstd>=1.0.0` on
  Python before 3.14, where Zstandard is in the standard library. The floor for
  `brotli` moves from 1.1 to 1.2.0 because older releases cannot bound
  decompression (`GHSA-2qfp-q593-8484`, a decompression bomb). Anyone who
  installed the extra and imported `zstandard` for their own use must now
  depend on it directly.
- The `-d`/`--data` help text no longer prints a literal `R|` prefix:
  `-d, --data DATA  R|JSON data for request body.` The marker belonged to a
  custom help formatter that was only ever attached to the top-level parser,
  never to the subcommands carrying the marker, so it leaked into the output it
  was meant to control. Both the formatter and the marker are gone.
- Corrected the documented exception mapping, which was wrong in two places.
  Retries exhausted against a server that kept returning a transient status
  raise `ResponseError` carrying the real status, not `HTTPConnectionError`.
  the adapter is built with `raise_on_status=False`, so the last response is
  reported rather than discarded. And a connect timeout raises
  `HTTPConnectionError`, not `HTTPClientError`, because
  `requests.exceptions.ConnectTimeout` subclasses `ConnectionError`. Only read
  timeouts reach `HTTPClientError`. Behaviour is unchanged; the documentation
  now matches it.
- `HTTPClient.allowed_methods` is now the attribute method validation
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

- A download drained through the progress bar (`show_progress`) now holds the
  body once in memory instead of twice at its peak, and finishes about a third
  faster for large bodies. The chunks were collected in a list and then joined,
  which built a second copy of the whole body; they are now written to an
  `io.BytesIO`, whose buffer becomes the response body directly. The response is
  identical: `.content`, `.text`, `.json()` and `iter_content` behave as before.
  This affects library callers; the CLI's own peak is dominated by rendering the
  text.
- `HTTPClient.__enter__` is annotated as returning the type of the client it was
  called on, not always `HTTPClient`. `with PatientClient() as client:`, the
  subclassing pattern the library guide documents, now type-checks as
  `PatientClient`, so a method the subclass adds is no longer reported as
  missing. Annotation only; there is no change at run time.
- The lock file now resolves requests 2.34.2, tqdm 4.70.1, certifi 2026.7.22,
  idna 3.20 and charset-normalizer 3.5.1. Two of these change behavior. requests
  2.34 no longer collapses a leading `//` in the URL path, so
  `http://host//a` is sent as `GET //a` where 2.33 sent `GET /a`; this fixes
  some presigned URLs. certifi 2026.7.22 trusts 121 root certificates where
  2026.2.25 trusted 137 (20 removed, 4 added), so a server chaining to one of
  the removed roots no longer verifies. Installs that do not use the lock file
  are unaffected, because the dependency floors did not move.
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
  is unchanged. Messages, codes, and stdout remain the same, but code that
  embedded `cli.main` and caught `SystemExit` to detect an error must check the
  return value instead.
- The seven verb methods (`get`, `post`, `put`, `patch`, `delete`, `head`,
  `options`) carry a one-line docstring pointing at `make_request` rather than
  restating its arguments and return value seven times over. Signatures and
  behaviour are unchanged; `help()` output is shorter.

### Added

- A "Security notes" section in the CLI reference, documenting behaviors that
  come from `requests` and that surprise people who put credentials on the
  command line: a `~/.netrc` entry overrides `-H "Authorization: ..."`, redirects
  drop `Authorization` but forward other custom headers to a new origin, secrets
  on the command line are visible in history and the process list, and `-v`
  prints credentials unredacted. Each was checked against the locked `requests`.
- ty as the project's type checker, with every rule at error level
  (`[tool.ty.rules] all = "error"`). It replaces mypy, whose `strict = true`
  configuration was the equivalent bar. Satisfying it added `@override`
  decorators (via `typing_extensions`, since the project floor is 3.10) to the
  test doubles in `tests/test_http_client.py` and corrected two of their
  signatures. `log_message` and `handle_error` collapsed their base class's
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
  urllib3 retries, so it can never observe a retry. The project shipped a false
  claim about `POST` retry behaviour on exactly that mistake. A session mounted
  with a test adapter now observes retries with no socket opened. The parameter
  is last and defaults to `None`, which builds the pooled, retrying session as
  before; a session passed in is used as it arrives, so `retries` does not apply
  to it, and the client closes only a session it built. See ADR 0004.
- ADR 0004, recording session injection. It supersedes only the mitigation in
  ADR 0001's Consequences, which documented the mock trap, but not its decision.

### Removed

- `types-requests`, from the dev dependencies. requests has shipped its own
  inline type annotations since 2.34.0, and the stubs package, frozen at
  requests 2.33, takes precedence over them. Its PyPI page now says to
  uninstall it. The dev group requires `requests>=2.34.2` in its place, so a
  resolution without the lock file cannot lose the annotations. This
  supersedes the note under mypy below that `types-requests` stays. The
  annotations exposed one real error in the tests, an override that returned
  the `ConnectionPool` base class where `HTTPConnectionPool` is expected; it is
  fixed.
- mypy, in favour of ty (see Added). The `[tool.mypy]` configuration is gone
  from `pyproject.toml`, including the `build/` and `dist/` excludes it needed.
  ty honours `.gitignore`, so build output is skipped without configuration.
  `types-requests` stays: ty reads the same stubs for `requests`.
- `snaffle.cli.show_examples` and the `suppress_output` parameter of
  `snaffle.cli.main`. Neither was part of the documented public API, which
  consists of `HTTPClient` and the three exceptions. The flag existed only to quiet
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
