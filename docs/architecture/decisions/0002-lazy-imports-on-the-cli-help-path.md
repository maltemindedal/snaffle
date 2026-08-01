# 2. Lazy imports on the CLI help path

- **Status:** Accepted
- **Date:** 2026-07-23 (shipped in 1.1.0)

## Context

`snaffle HELP` printed a static block of text and exited. It took 238 ms to do
it, because importing the package imported `HTTPClient`, which imported
`requests`, which costs well over 100 ms of interpreter start-up on its own.
`tqdm` added roughly 15 ms more.

Every invocation paid for the network stack, including the ones that never
touched the network: `HELP`, `--help`, and any argument error.

## Decision

Defer the import of the HTTP stack to the point where a request is actually
made. Three places:

**`cli.main` imports `HTTPClient` after the help branch returns.** The import
sits below the `if not command or command == "HELP"` early return, so help
paths and argparse errors never reach it.

**`snaffle/__init__.py` resolves `HTTPClient` through a module-level
`__getattr__` (PEP 562).** `import snaffle` no longer imports `requests`;
`from snaffle import HTTPClient` still works and triggers the import on first
access. The exceptions are imported eagerly — `exceptions.py` has no
dependencies, so it is free.

**`snaffle._download` imports `tqdm` inside the function that builds the bar.**
A run without `--progress` never pays for it. (This lived on
`HTTPClient._create_progress_bar` until the progress-bar download moved into its
own module; the deferral is unchanged, only its address.)

**The same `__getattr__` resolves `__version__` from `importlib.metadata`.**
Added later, when the hand-maintained `__version__` string was replaced by a
read of the installed distribution's metadata. Deferring it keeps that read off
every `import snaffle`, where nothing needs it.

## Consequences

CLI start-up for `snaffle HELP` fell from 238 ms to 80 ms.

> **TODO(verify):** these figures come from the 1.1.0 changelog entry
> (2026-07-23). No benchmark script is committed, so they cannot be reproduced
> from the repository.

The saving is fragile. Any new module-scope `import requests` anywhere on the
import path silently undoes it, and nothing about the code makes that obvious.
Two things guard against it:

- `tests/test_cli.py::test_help_path_does_not_import_requests` spawns a
  subprocess, runs `main(['HELP'])`, and fails if `requests` is in
  `sys.modules` afterwards.
- `tests/test_init.py::test_import_does_not_pull_in_requests` does the same for
  a bare `import snaffle`, covering library users rather than the CLI.
- `CONTRIBUTING.md` states the convention: anything that would import
  `requests` at module scope should be deferred.

Static analysis sees less. `__getattr__` returns `Any`, so `HTTPClient` and
`__version__` are typed for consumers only via the `TYPE_CHECKING` block in
`__init__.py`. That block exists solely to keep the annotations visible to type
checkers. `cli.py` uses the same device to annotate `_emit_response` with
`requests.Response` without importing `requests` at run time — a
`TYPE_CHECKING` import is not a violation of this ADR, because it never
executes.

Reading the code is marginally harder: four imports sit somewhere other than
the top of their file, each with a comment saying why.

## Alternatives considered

**Accept the start-up cost.** Defensible for a long-running program, poor for a
CLI whose most common no-op invocation is help.

**Move the examples text into a separate module with no imports.** Would have
fixed `HELP` but not `--help` or argument errors, which go through argparse in
`cli.py` and would still have pulled in the client.

**Drop `tqdm`** and hand-roll a progress bar to avoid the dependency. Not worth
it — the lazy import already removes the cost for runs that do not use it.
