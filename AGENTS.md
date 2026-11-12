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

CI's `changelog` job runs once, against the merge-base with `origin/main`:

```bash
.agents/skills/verify-snaffle/scripts/changelog.sh
```

End-to-end check with kept evidence (the gate above, then `snaffle GET`
against a local server; see `.agents/skills/verify-snaffle/SKILL.md`):

```bash
.agents/skills/verify-snaffle/scripts/verify.sh all
```

One class, or one method:

```bash
uv run python -X dev -W error -m unittest tests.test_http_client.TestRetryPolicy
uv run python -X dev -W error -m unittest tests.test_http_client.TestRetryWithoutASocket.test_post_is_retried_when_the_connection_never_opens
```

The runner is `unittest` and the only type checker is `ty`; `pytest` and `mypy`
are not installed. Keep `types-requests` out too: requests 2.34 ships its own
annotations, and the stubs, frozen at 2.33, would shadow them.

## Rules

Each rule and what fails when it is broken. A check names the fix in its own
error, so a rule a check enforces is stated here in one line. "Review only"
marks a judgement call that nothing fails on: read those before the change.

Tests:

| Rule | Enforced by |
| --- | --- |
| Every fix ships a test that fails without it. Run the new test against the unfixed code before committing: several earlier tests passed either way. | Review only. `.agents/skills/verify-snaffle/scripts/replay.sh <sha>` runs today's guards against an older commit. |
| Test retries below `requests.Session.request`: pass a session (`TestRetryWithoutASocket`), use a real server (`TestRetryAgainstRealServer`) or check the `Retry` object (`TestRetryPolicy`). | `tests/test_guard_no_session_patch.py` |
| Every test module imports `setUpModule` from `tests/_isolation.py`, so proxy and `TQDM_*` settings on the machine cannot reach a test. | `tests/test_guard_isolation.py` |
| Tests talk only to loopback. | Review only |
| Open clients in tests with `with HTTPClient(...)`. | `verify.sh test` fails on a `ResourceWarning` line. CI does not: see Gotchas. |

Code:

| Rule | Enforced by |
| --- | --- |
| `import snaffle` and the CLI help path do not load `requests`. | `test_import_does_not_pull_in_requests` in `tests/test_init.py`, `test_help_path_does_not_import_requests` in `tests/test_cli.py` |
| Nor do they load `tqdm`. Annotate with a `TYPE_CHECKING` import and import at call time with a comment citing ADR 0002, as `cli.py` and `_download.py` do. | Review only |
| Translate `requests` and urllib3 exceptions in `HTTPClient.make_request` only, with `raise ... from e`. | Review only |
| Send server-chosen text bound for stdout through `_terminal.for_stdout`, and request arguments printed by `--verbose` through `_redacted()`. | Review only |
| Every public module, class and function, dunders included, has a Google-style docstring (`Args:`, `Returns:`, types in parentheses); attributes get `#:` comments. | Review only (ruff's `D` rules are off) |
| First-party imports are absolute: `from snaffle.exceptions import ...`. | Review only |
| Fix lint and type findings instead of suppressing them. An unavoidable suppression names one rule: `# ty: ignore[<rule>]` or `# noqa: <code>`. | `ruff check` (`PGH004` for a bare `# noqa`). A bare `# ty: ignore` is review only. |
| Leave platform defaults implicit. PR #25 removed a Dependabot `cooldown` that only restated the default. | Review only |

Public API and versions:

| Rule | Enforced by |
| --- | --- |
| Public means the names in `snaffle.__all__`, `ProgressBar` from `snaffle.http_client`, documented class constants and attributes (users override them in subclasses), the `[VERBOSE]` line format, CLI output, and exit codes. Breaking any of it is a major version. | Review only |
| Define each public name in its documented module. | `tests/test_guard_public_modules.py` |
| A lazy public name is in `__all__`, the `TYPE_CHECKING` block, `__getattr__` and the docstring list in `src/snaffle/__init__.py`. | `tests/test_guard_init_lists.py` |
| The defaults the CLI help states are the client's. | `test_the_default_timeout_is_the_clients`, `test_the_stated_progress_threshold_is_the_clients` in `tests/test_cli.py` |
| The version lives only in `pyproject.toml`. A release bumps it, runs `uv lock`, dates the `CHANGELOG.md` `[Unreleased]` section (with its link reference) below a fresh empty one, and updates the table in `SECURITY.md`. | Review only. `uv sync --locked` fails on a stale `uv.lock`. |

Docs and changelog:

| Rule | Enforced by |
| --- | --- |
| Docs keep reasons, decisions and how-to. They do not copy by hand what the code states (a count, a constant's value, a default, a status list, a method list or `--help` output). Name the code (`HTTPClient.RETRY_STATUSES`), or add a block to `BLOCKS` in `tests/test_docs_sync.py` and run `uv run python -m tests.test_docs_sync --write`. | `tests/test_docs_sync.py` for the generated blocks. A copy outside them is review only. |
| A behaviour claim that must stay in prose is a `console` or `pycon` block on a page in `PAGES` in `tests/test_docs.py`. | `tests/test_docs.py` |
| A user-visible change gets a full paragraph under `## [Unreleased]` in `CHANGELOG.md`, in `### Security`, `Fixed`, `Changed`, `Added` or `Removed`, saying what changes for the user. Tooling, CI, test, docs and lock-only changes get none. | `.agents/skills/verify-snaffle/scripts/changelog.sh` (in `verify.sh test` and CI's `changelog` job) when `src/snaffle/` changes. A change no user can notice ends a commit message with `Changelog: none (<reason>)`. |
| A retry or exception change updates the tests that pin it, and ADR 0001 when the decision itself changes. | `TestRetryPolicy`, `TestRetryWithoutASocket`, the `pycon` examples and the generated retry table in `docs/reference/python-api.md` |
| A new HTTP method or CLI flag: `HTTPClient.ALLOWED_METHODS` and a verb method, or the argument and its help text in `cli.py`, plus `COMMANDS` and `EXAMPLES`. `docs/reference/cli.md` changes by hand only for behaviour the help text cannot say. | `tests/test_docs_sync.py` for the commands, flags and method tables. The rest is review only. |
| A change to the supported Python range updates the CI matrix, `requires-python`, classifiers and ruff `target-version`, plus the mentions in `README.md`, `CONTRIBUTING.md` and `docs/getting-started.md`. | Review only |
| A new file under `docs/` gets a row in `docs/README.md`. | Review only |

Prose in docs, docstrings, comments and commits (the owner rewrote 27 files of
agent prose to get it):

| Rule | Enforced by |
| --- | --- |
| No em dash (or ` -- ` standing in for one), "seam", "deliberately", or "surface" for an API. | `tests/test_guard_prose.py` |
| Short declarative sentences in plain words. Wrap Markdown prose at about 80 columns. | Review only |
| Commit subjects are imperative and sentence case, with no `feat:`-style prefix. A fix, docs or tests commit ends with its kind in parentheses: `(bug fix)`, `(security fix)`, `(review fix)`, `(docs)`, `(tests)`. | Review only |
| PR bodies give the exact verification commands with their results, and name any judgement call (such as whether a change is breaking) for the owner. | Review only |

## Cursor Cloud specific instructions

- `.cursor/environment.json` installs uv 0.12.17 into `/usr/local/bin` and
  runs `/usr/local/bin/uv` explicitly, so an older uv earlier on `PATH` does
  not trigger a reinstall on every start. It also installs `unzip`, which the
  wheel check in `verify.sh` needs.
- The uv pin lives in two places: the `install` script in
  `.cursor/environment.json` and `version:` under `astral-sh/setup-uv` in
  `.github/workflows/ci.yml`. Change both together;
  `tests/test_tooling_pins.py` fails when they differ.
- Sync with `uv sync --locked --group dev --extra speedups`, as CI does.
- Python is not pinned: uv picks the newest interpreter it finds (3.13 on the
  cloud image), while CI tests 3.10 to 3.14. Do not add a `.python-version`
  or another pin unless the pin test covers it.
- No services are needed. The CLI check starts its own `http.server` on a free
  127.0.0.1 port and stops it.
- The gate is `.agents/skills/verify-snaffle/scripts/verify.sh all`; it must
  end in `RESULT: PASS (all)`.

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
- The `github-advanced-security` check fails for platform reasons (model
  support, quota) that no repository change fixes. Say so in the PR.

## Docs

Before changing any of these, read its decision record in
`docs/architecture/decisions/` (a new decision gets a record in the same shape):

- Retries, backoff, retried statuses, pooling or streaming: ADR 0001.
- Imports in `__init__.py`, `cli.py`, `_terminal.py`, `exceptions.py`: ADR 0002.
- Module names, packaging or entry points: ADR 0003.
- `HTTPClient.__init__`, `close()` or who owns the session: ADR 0004.

Before adding a feature or moving code between modules, read
`docs/architecture/overview.md` for module responsibilities and non-goals.
