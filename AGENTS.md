# AGENTS.md

Snaffle is a command-line HTTP client and the importable `HTTPClient` behind
it, a thin layer over `requests` and urllib3. A change here usually protects the
retry contract, the exception mapping, the lazy imports, the typed public API,
or the defences against a hostile server (terminal escaping, redaction).

## Commands

Run everything from the repository root through uv. Sync exactly as CI does:

```bash
uv sync --locked --group dev --extra speedups
```

The README's shorter `uv sync --group dev` uninstalls brotli, and
`TestSpeedupsExtra` then skips without failing.

The pre-PR gate. CI runs these on Python 3.10 to 3.14, then checks that the
built wheel ships `snaffle/py.typed`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run python -X dev -W error -m unittest discover tests
uv build
```

One class, or one method:

```bash
uv run python -X dev -W error -m unittest tests.test_http_client.TestRetryPolicy
uv run python -X dev -W error -m unittest tests.test_http_client.TestRetryWithoutASocket.test_post_is_retried_when_the_connection_never_opens
```

The runner is `unittest` and the only type checker is `ty`; `pytest` and `mypy`
are not installed. Keep `types-requests` out too: requests 2.34 ships its own
annotations, and the stubs, frozen at 2.33, would shadow them.

## Conventions

Tests:

- Every fix ships a test that fails without it. Run the new test against the
  unfixed code before committing: several earlier tests passed either way and
  needed follow-up commits to make them able to fail.
- Test retries below `requests.Session.request`. A mock of it sits above the
  adapter where urllib3 retries, and once let a false claim about `POST`
  retries ship. Extend `TestRetryWithoutASocket`, `TestRetryAgainstRealServer`
  or `TestRetryPolicy` in `tests/test_http_client.py`.
- Tests talk only to loopback. A new test module that opens sockets clears the
  `*_proxy` variables, as `setUpModule` in `test_http_client.py` does, so a
  proxy on the developer's machine cannot reroute loopback requests.

Code:

- `import snaffle` and the CLI help path load neither `requests` nor `tqdm`.
  Annotate with a `TYPE_CHECKING` import and import at call time with a comment
  citing ADR 0002, as `cli.py` and `_download.py` do. Tests guard `requests`
  only; nothing catches an eager `tqdm`.
- Translate `requests` and urllib3 exceptions in `HTTPClient.make_request` only,
  with `raise ... from e`.
- Send server-chosen text bound for stdout through `_terminal.for_stdout`, and
  request arguments printed by `--verbose` through `_redacted()`.
- Every public module, class and function, dunders included, has a
  Google-style docstring (`Args:`, `Returns:`, types in parentheses);
  attributes get `#:` comments. Ruff's `D` rules are off, so only review checks.
- First-party imports are absolute: `from snaffle.exceptions import ...`.
- Fix lint and type findings instead of suppressing them. An unavoidable
  suppression names one rule: `# ty: ignore[<rule>]` or `# noqa: <code>`.
- Leave platform defaults implicit. PR #25 removed a Dependabot `cooldown` that
  only restated the default.

Public API and versions:

- Public means the names in `snaffle.__all__`, `ProgressBar` from
  `snaffle.http_client`, documented class constants and attributes (users
  override them in subclasses), the `[VERBOSE]` line format, CLI output, and
  exit codes. Breaking any of it is a major version. Define each public name in
  its documented module: `ProgressBar` came back out of `_download.py` because
  its `__module__` named the private home.
- A new lazy public name touches `__all__`, the `TYPE_CHECKING` block,
  `__getattr__` and the docstring list in `src/snaffle/__init__.py`, plus
  `docs/reference/python-api.md`.
- The version lives only in `pyproject.toml`. A release bumps it, runs
  `uv lock`, dates the `CHANGELOG.md` `[Unreleased]` section (with its link
  reference) below a fresh empty one, and updates the table in `SECURITY.md`.

Update the docs in the same change as the code:

- Retry or exception behaviour: the `HTTPClient` class docstring,
  `docs/reference/python-api.md`, ADR 0001, `docs/architecture/overview.md`
  and `docs/guides/using-as-a-library.md`.
- A new HTTP method or CLI flag: `HTTPClient.ALLOWED_METHODS` and a verb
  method, `COMMANDS` and `EXAMPLES` in `cli.py`, the counts in `README.md`, and
  the `--help` blocks pasted into `docs/reference/cli.md` (regenerate them from
  real output).
- The supported Python range: the CI matrix, `requires-python`, classifiers and
  ruff `target-version`, plus the mentions in `README.md`, `CONTRIBUTING.md`,
  `docs/getting-started.md` and `docs/reference/cli.md`.
- A new file under `docs/` gets a row in `docs/README.md`.
- User-visible changes go in `CHANGELOG.md` under `## [Unreleased]`, in
  `### Security`, `Fixed`, `Changed`, `Added` or `Removed`, as full paragraphs
  saying what changes for the user. Tooling, CI and lock-only changes get none.

Prose in docs, docstrings, comments and commits (the owner rewrote 27 files of
agent prose to get it):

- Short declarative sentences in plain words: "boundary", not "seam"; "API",
  not "surface"; drop "deliberately". Join clauses with a full stop, colon or
  parentheses; the tree has no em dashes. Wrap Markdown prose at about 80
  columns.
- Commit subjects are imperative and sentence case, with no `feat:`-style
  prefix. A fix, docs or tests commit ends with its kind in parentheses:
  `(bug fix)`, `(security fix)`, `(review fix)`, `(docs)`, `(tests)`.
- PR bodies give the exact verification commands with their results, and name
  any judgement call (such as whether a change is breaking) for the owner.

## Gotchas

- `ruff format --check .` covers Markdown too, this file and `.agents/skills/`
  included, so a badly formatted Python code block in any `.md` file fails CI.
- Commit `uv.lock` with any version or dependency change in `pyproject.toml`,
  made by `uv lock`. A plain `uv run` rewrites the lock silently, and CI's
  `uv sync --locked` fails on every leg when it is stale.
- `-W error` does not fail the run on an unclosed socket, whatever
  `CONTRIBUTING.md` says: the leak prints an `Exception ignored` line naming
  `ResourceWarning`, and the run still reports `OK`. Open clients in tests with
  `with HTTPClient(...)`, and read the output for that line.
- `docs/reference/python-api.md` says exhausted connection retries raise
  `RetryError`; the `__cause__` is `requests.exceptions.ConnectionError`.
- The `github-advanced-security` check fails for platform reasons (model
  support, quota) that no repository change fixes. Say so in the PR.
- `.agents/skills/dataverse-python-production-code` is written for the
  Dataverse SDK. Where its retry advice differs, ADR 0001 governs here.

## Docs

Before changing any of these, read its decision record in
`docs/architecture/decisions/` (a new decision gets a record in the same shape):

- Retries, backoff, retried statuses, pooling or streaming: ADR 0001.
- Imports in `__init__.py`, `cli.py`, `_terminal.py`, `exceptions.py`: ADR 0002.
- Module names, packaging or entry points: ADR 0003.
- `HTTPClient.__init__`, `close()` or who owns the session: ADR 0004.

Before adding a feature or moving code between modules, read
`docs/architecture/overview.md` for module responsibilities and non-goals.
